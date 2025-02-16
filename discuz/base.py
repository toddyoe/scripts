import logging
import re
from http.cookies import SimpleCookie

import ddddocr
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s: %(message)s",
)

# reference: https://github.com/nodeloc/hostloc_auto
class Login:
    def __init__(
        self, hostname: str, username: str, password: str, cookie: str = "", questionid: str = "0", answer: str = None
    ):
        self.session = requests.session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36"
            }
        )
        self.hostname = hostname
        self.username = str(username)
        self.password = str(password)

        self.questionid = questionid
        self.answer = answer
        self.cookie = cookie
        self.ocr = ddddocr.DdddOcr()

    def form_hash(self):
        content = self.session.get(f"https://{self.hostname}/member.php?mod=logging&action=login").text
        logininfo = re.search(r'<div id="main_messaqge_(.+?)">', content)

        if logininfo is not None:
            loginhash = re.search(r'<div id="main_messaqge_(.+?)">', content).group(1)
        else:
            loginhash = ""

        formhash = re.search(r'<input type="hidden" name="formhash" value="(.+?)" />', content).group(1)
        logging.info(f"loginhash：{loginhash}，formhash：{formhash}，hostname：{self.hostname}")

        return loginhash, formhash

    def verify_code_once(self):
        rst = self.session.get(
            f"https://{self.hostname}/misc.php?mod=seccode&action=update&idhash=cSA&0.3701502461393815&modid=member::logging"
        ).text
        update = re.search(r"update=(.+?)&idhash=", rst).group(1)

        code_headers = {
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "hostname": f"{self.hostname}",
            "Referer": f"https://{self.hostname}/member.php?mod=logging&action=login",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36",
        }
        rst = self.session.get(
            f"https://{self.hostname}/misc.php?mod=seccode&update={update}&idhash=cSA", headers=code_headers
        )

        return self.ocr.classification(rst.content)

    def verify_code(self, num=10):
        while num > 0:
            num -= 1
            code = self.verify_code_once()
            verify_url = f"https://{self.hostname}/misc.php?mod=seccode&action=check&inajax=1&modid=member::logging&idhash=cSA&secverify={code}"
            res = self.session.get(verify_url).text

            if "succeed" in res:
                logging.info(f"验证码识别成功，验证码：{code}，hostname：{self.hostname}")
                return code
            else:
                logging.info(f"验证码识别失败，重新识别中。hostname：{self.hostname}")

        logging.error(f"验证码获取失败，请增加验证次数或检查当前验证码识别功能是否正常。hostname：{self.hostname}")
        return ""

    def account_login_without_verify(self):
        loginhash, formhash = self.form_hash()
        login_url = f"https://{self.hostname}/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1"
        formData = {
            "formhash": formhash,
            "referer": f"https://{self.hostname}/",
            "username": self.username,
            "password": self.password,
            "handlekey": "ls",
        }

        content = self.session.post(login_url, data=formData).text
        if "succeed" in content:
            logging.info(f"登陆成功，hostname：{self.hostname}")
            return True
        else:
            logging.info(f"登陆失败，请检查账号或密码是否正确。hostname：{self.hostname}")
            return False

    def account_login(self):
        if not self.username or not self.password:
            logging.info(f"登陆失败，用户名或密码为空。hostname：{self.hostname}")
            return False

        try:
            if self.account_login_without_verify():
                return True
        except Exception:
            logging.error(f"存在验证码，登陆失败，准备获取验证码中。hostname：{self.hostname}", exc_info=True)

        code = self.verify_code()
        if code == "":
            return False

        loginhash, formhash = self.form_hash()
        login_url = f"https://{self.hostname}/member.php?mod=logging&action=login&loginsubmit=yes&loginhash={loginhash}&inajax=1"
        body = {
            "formhash": formhash,
            "referer": f"https://{self.hostname}/",
            "loginfield": self.username,
            "username": self.username,
            "password": self.password,
            "questionid": self.questionid,
            "answer": self.answer,
            "cookietime": 2592000,
            "seccodehash": "cSA",
            "seccodemodid": "member::logging",
            "seccodeverify": code,
        }

        content = self.session.post(login_url, data=body).text
        if "succeed" in content:
            logging.info(f"登陆成功，hostname：{self.hostname}")
            return True
        else:
            logging.info(f"登陆失败，请检查账号或密码是否正确。hostname：{self.hostname}")
            return False

    def cookies_login(self):
        try:
            sc = SimpleCookie()
            sc.load(self.cookie)

            # 合并cookie
            self.session.cookies.update({k: v.value for k, v in sc.items()})

            response = self.session.get(f"https://{self.hostname}/home.php?mod=space").text

            if "退出" in response and "登录" not in response:
                logging.info(f"Cookie有效，跳过登录。hostname：{self.hostname}")
                return True
        except Exception:
            logging.warning(f"Cookie失效，使用账号密码登录。hostname：{self.hostname}")

        return False

    def go_home(self):
        return self.session.get(f"https://{self.hostname}/forum.php").text

    def get_conis(self):
        try:
            response = self.session.get(
                f"https://{self.hostname}/home.php?mod=spacecp&ac=credit&showcredit=1&inajax=1&ajaxtarget=extcreditmenu_menu"
            ).text
            coins = re.search(r'<span id="hcredit_2">(.+?)</span>', response).group(1)
            logging.info(f"当前金币数量：{coins}，hostname：{self.hostname}")
        except Exception:
            logging.error(f"获取金币数量失败！hostname：{self.hostname}", exc_info=True)

    def login(self) -> bool:
        try:
            if self.cookie and self.cookies_login():
                logging.info(f"成功使用Cookie登录，hostname：{self.hostname}")
            else:
                self.account_login()

            content = self.go_home()
            self.post_formhash = re.search(r'<input type="hidden" name="formhash" value="(.+?)" />', content).group(1)
            credit = re.search(r' class="showmenu">(.+?)</a>', content).group(1)
            logging.info(f"{credit}，提交文章formhash：{self.post_formhash}，hostname：{self.hostname}")

            self.get_conis()
            return True
        except Exception:
            logging.error(f"失败，发生了一个错误！hostname：{self.hostname}", exc_info=True)
            return False
