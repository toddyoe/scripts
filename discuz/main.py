import json
import logging
import os
import random
import re
import sys
import time
import typing
from concurrent import futures

import requests

import base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s: %(message)s",
)


class Discuz:
    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        cookie: str = "",
        questionid: str = "0",
        answer: str = None,
        pub_url: str = "",
    ):
        self.hostname = hostname
        if pub_url != "":
            self.hostname = self.get_host(pub_url)

        self.discuz_login = base.Login(self.hostname, username, password, cookie, questionid, answer)

    def login(self) -> bool:
        success = self.discuz_login.login()

        if success:
            self.session = self.discuz_login.session
            self.formhash = self.discuz_login.post_formhash

        return success

    def get_host(self, pub_url: str) -> str:
        response = requests.get(pub_url)
        response.encoding = "utf-8"

        url = re.search(r'a href="https://(.+?)/".+?>.+?入口</a>', response.text)
        if url != None:
            url = url.group(1)
            logging.info(f"获取到最新的论坛地址：https://{url}")
            return url
        else:
            logging.error(f"获取失败，请检查发布页 {pub_url} 是否可用")
            return self.hostname

    def go_home(self) -> str:
        return self.session.get(f"https://{self.hostname}/forum.php").text

    def go_hot(self) -> str:
        return self.session.get(f"https://{self.hostname}/forum-45-1.html").text

    def generate_random_numbers(self, start: int, end: int, count: int) -> list[int]:
        random_numbers = []
        for _ in range(count):
            random_number = random.randint(start, end)
            random_numbers.append(random_number)

        return random_numbers

    def signin(self) -> None:
        signin_url = f"https://{self.hostname}"
        self.session.get(signin_url)

        formhash = self.discuz_login.post_formhash
        url = f"https://{self.hostname}/k_misign-sign.html"
        if formhash:
            url += (
                f"?operation=qiandao&format=global_usernav_extra&formhash={formhash}&inajax=1&ajaxtarget=k_misign_topb"
            )

        self.session.get(url)

    def visit_home(self, start: int = 1, end: int = 10000, count: int = 10) -> None:
        start, count = max(1, start), max(count, 0)
        end = max(count, end)

        random_numbers = self.generate_random_numbers(start, end, count)
        for number in random_numbers:
            time.sleep(5)
            signin_url = f"https://{self.hostname}/space-uid-{number}.html"

            self.session.get(signin_url)


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def extract_domain(url: str, include_protocal: bool = False) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url)

    if include_protocal:
        return url[:end]

    return url[start + 2 : end]


def multi_thread_run(func: typing.Callable, tasks: list, num_threads: int = None) -> list:
    if not func or not tasks or not isinstance(tasks, list):
        return []

    if num_threads is None or num_threads <= 0:
        num_threads = min(len(tasks), (os.cpu_count() or 1) * 2)

    funcname = getattr(func, "__name__", repr(func))

    results, starttime = [None] * len(tasks), time.time()
    with futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        if isinstance(tasks[0], (list, tuple)):
            collections = {executor.submit(func, *param): i for i, param in enumerate(tasks)}
        else:
            collections = {executor.submit(func, param): i for i, param in enumerate(tasks)}

        items = futures.as_completed(collections)
        for future in items:
            try:
                result = future.result()
                index = collections[future]
                results[index] = result
            except Exception as e:
                logging.error(f"function {funcname} execution generated an exception: {e}")

    logging.info(
        f"[Concurrent] multi-threaded execute [{funcname}] finished, count: {len(tasks)}, cost: {time.time()-starttime:.2f}s"
    )

    return results


def checkin(domain: str, username: str, password: str, cookie: str = "") -> None:
    domain, username, password, cookie = trim(domain), trim(username), trim(password), trim(cookie)
    hostname = extract_domain(url=domain, include_protocal=False)

    if not hostname or (not cookie and (not username or not password)):
        logging.info(f"跳过 {domain} 签到，站点/用户名/密码或 cookie 为空")
        return

    discuz = Discuz(hostname, username, password, cookie)

    # 登录
    success = discuz.login()
    if not success:
        return

    # 签到
    discuz.signin()

    # 访问其他用户主页
    discuz.visit_home()


def load_config(url: str) -> list[list[str]]:
    if not url:
        return []

    response = requests.get(url=url, timeout=30)
    if response.status_code != 200:
        logging.error(f"获取任务配置失败，状态码：{response.status_code}")
        return []

    content = response.text
    try:
        data = json.loads(content)
        if not data or not isinstance(data, dict):
            return []

        tasks = list()
        for domain, accounts in data.items():
            domain = trim(domain)
            if not domain or not accounts or not isinstance(accounts, list):
                continue

            for item in accounts:
                if not item or not isinstance(item, dict):
                    continue

                username = trim(item.get("username", ""))
                password = trim(item.get("password", ""))
                cookie = trim(item.get("cookie", ""))

                tasks.append([domain, username, password, cookie])

        return tasks
    except:
        logging.error(f"解析配置任务失败")
        return []


if __name__ == "__main__":
    url = trim(os.environ.get("TASK_CONF_URL", ""))
    if not re.match(r"^https?://", url, flags=re.I):
        logging.error(f"任务配置链接无效，请检查确认")
        sys.exit(1)

    tasks = load_config(url=url)
    if tasks:
        multi_thread_run(func=checkin, tasks=tasks)
