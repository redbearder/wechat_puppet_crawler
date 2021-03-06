# Android environment
import unittest
from appium import webdriver
import time
import redis
import threading
import requests
from elasticsearch import Elasticsearch
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from sqlalchemy import Column, Integer, String, DateTime, func, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
from lxml import etree

r = redis.Redis(host="localhost", port=6379, db=0)
engine = create_engine(
    "mysql+pymysql://root@localhost/wechat_puppet_crawler?charset=utf8mb4",
    echo=True)
Session = sessionmaker(bind=engine)

es = Elasticsearch()

from selenium import webdriver as selenium_webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

chrome_options = Options()
# chrome_options.add_argument("--disable-extensions")
# chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--headless")
chrome_options.add_argument("window-size=1920,1080")
browserdriver = selenium_webdriver.Chrome(options=chrome_options)
# browserdriver.maximize_window()

desired_caps = {}
desired_caps["appActivity"] = ".ui.LauncherUI"
desired_caps["appPackage"] = "com.tencent.mm"
desired_caps["automationName"] = "UiAutomator2"
desired_caps["deviceName"] = "127.0.0.1:7555"
desired_caps["platformName"] = "Android"
desired_caps["platformVersion"] = "6.0.1"
desired_caps["resetKeyboard"] = True
desired_caps["newCommandTimeout"] = "0"
desired_caps["connectHardwareKeyboard"] = True
desired_caps["noReset"] = True

chatlistid = "com.tencent.mm:id/b9i"
expandid = "com.tencent.mm:id/a9j"
textboxid = "com.tencent.mm:id/aom"
sendbtnid = "com.tencent.mm:id/aot"

mp_name_id = "com.tencent.mm:id/a8p"
mp_name_list = ["央视新闻"]

last_article_title = None

session = Session()


class Article(Base):
    __tablename__ = "article"

    id = Column(Integer, primary_key=True, autoincrement=True)
    articleid = Column(String(100), unique=True)
    title = Column(String(250))
    url = Column(String(250))
    image = Column(String(250))
    account = Column(String(250))
    author = Column(String(250))
    description = Column(String(250))
    createdAt = Column(DateTime,
                       default=func.now(),
                       comment="user create datetime")
    updatedAt = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        comment="user update datetime",
    )


class Channel(Base):
    __tablename__ = "channel"

    channelid = Column(Integer, primary_key=True, autoincrement=True)
    channelname = Column(String(100), unique=True)
    channellogo = Column(String(250))
    channelcover = Column(String(250), nullable=True)
    channelsubcount = Column(Integer, default=0)
    createdAt = Column(DateTime,
                       default=func.now(),
                       comment="channel create datetime")
    updatedAt = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        comment="channel update datetime",
    )


def crawler():
    while True:
        try:
            l = r.lpop("link")
            if not l:
                time.sleep(3)
                continue
            # crawl l
            o = urlparse(l)
            docid = o.path[3:]
            all_exist_article_list = (session.query(Article).filter(
                Article.articleid == docid).all())
            if len(all_exist_article_list) > 0:
                continue
            res = requests.get(l)
            content = res.text

            soup = BeautifulSoup(content, "html.parser")
            if len(soup.select("iframe")) > 0:
                browserdriver.get(l.decode())
                # print(browserdriver.page_source.encode("utf-8"))
                html = browserdriver.find_element_by_tag_name("html")
                time.sleep(1)
                last_scrollY = None
                scrollHeight = browserdriver.execute_script(
                    "return document.body.scrollHeight;")
                while True:
                    html.send_keys(Keys.PAGE_DOWN)
                    time.sleep(1)
                    scrollY = browserdriver.execute_script(
                        "return window.scrollY")
                    if scrollY == last_scrollY:
                        break
                    last_scrollY = scrollY

                print("Reached to the bottom of the page")
                content = browserdriver.page_source
                content = content.replace("&amp;tp=webp", "")
                soup = BeautifulSoup(content, "html.parser")
                iframes = soup.select("iframe")
                for iframe in iframes:
                    if iframe.get("src"):
                        iframe.attrs["src"] = f"https:{iframe.attrs['src']}"
                pass
            else:
                soup.title.string = soup.select_one(
                    'meta[property="og:title"]').get("content")
                imglist = soup.select("img")
                for img_element in imglist:
                    if img_element.get("data-src"):
                        img_element.attrs["src"] = img_element.attrs[
                            "data-src"]
                pass

            # xpath
            # selector = etree.HTML(content)
            # links = selector.xpath('//h4/a/text()')
            article_title = soup.select_one('meta[property="og:title"]').get(
                "content")
            article_description = soup.select_one(
                'meta[property="og:description"]').get("content")
            article_author = soup.select_one(
                'meta[property="og:article:author"]').get("content")
            article_url = soup.select_one('meta[property="og:url"]').get(
                "content")
            article_image = soup.select_one('meta[property="og:image"]').get(
                "content")
            article_account = soup.select_one(".profile_nickname").string

            script_list = soup.select("script")
            for script_element in script_list:
                script_element.decompose()

            article_content = soup.prettify()

            es.index(
                index="article",
                id=docid,
                body={
                    "title": article_title,
                    "articleid": docid,
                    "description": article_description,
                    "author": article_author,
                    "url": article_url,
                    "image": article_image,
                    "account": article_account,
                    "content": article_content,
                },
            )

            new_a = Article(
                title=article_title,
                articleid=docid,
                url=article_url,
                image=article_image,
                account=article_account,
                author=article_author,
                description=article_description,
            )
            session.add(new_a)

            # get hd_head_img from js
            channelRes = Channel.query.filter_by(
                channelname=article_account).first()
            if not channelRes:
                channellogo = ''
                ss = soup.find_all('script')
                import re
                for s in ss:
                    if "hd_head_img" in s.text:
                        m = re.findall('var hd_head_img = (.*?);', s.text)
                        channellogo = m[0].split('||')[0]
                        channellogo = channellogo.replace('"', '')
                        pass
                new_c = Channel(
                    channelname=article_account,
                    channellogo=channellogo,
                )
                session.add(new_c)
            session.commit()
        except:
            continue
    pass


if __name__ == "__main__":
    threading.Thread(target=crawler).start()

    while True:
        try:
            driver = webdriver.Remote("http://localhost:4723/wd/hub",
                                      desired_caps)
            chatwlist = []
            while len(chatwlist) == 0:
                chatwlist = driver.find_elements_by_id(chatlistid)

            for chatw in chatwlist:
                if chatw.text == "订阅号消息":
                    chatw.click()
                    time.sleep(3)
                    expand_element_list = driver.find_elements_by_id(expandid)
                    for expand_ele in expand_element_list:
                        expand_ele.click()
                        time.sleep(1)
                    # article_element_list = driver.find_elements_by_id(
                    # 'com.tencent.mm:id/a9n')
                    article_element_list = driver.find_elements_by_xpath(
                        '//android.widget.ImageView[@content-desc="图片"]')
                    if len(article_element_list) == 0:
                        break
                    for e in article_element_list:
                        e.click()
                        time.sleep(10)
                        opbtn = driver.find_element_by_id(
                            "com.tencent.mm:id/l0")
                        opbtn.click()
                        time.sleep(3)
                        copybtns = driver.find_elements_by_id(
                            "com.tencent.mm:id/d0")
                        copybtnidx = 0
                        for btn in copybtns:
                            if btn.text == "复制链接":
                                btn.click()
                                time.sleep(1)
                                r.lpush("link", driver.get_clipboard())
                                break
                            copybtnidx += 1

                        if copybtnidx == 0:
                            backbtn = driver.find_element_by_id(
                                "com.tencent.mm:id/lc")
                            backbtn.click()
                        backbtn = driver.find_element_by_id(
                            "com.tencent.mm:id/lc")
                        backbtn.click()
                        time.sleep(3)
                        pass

        except Exception as e:
            continue

        print("end one loop")
        time.sleep(60)
