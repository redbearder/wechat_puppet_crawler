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

tabbtnsid = 'com.tencent.mm:id/ddm'
top_contact_lines_id = 'com.tencent.mm:id/a80'
mp_account_lines_id = 'com.tencent.mm:id/aai'

mp_account_name_list = [
    'KIKS',
    '潮人',
    'NOWRE',
    'HYPEBEAST',
    'YOHO潮流志',
    'DAZED OFFICAL',
    'MiLK志',
    '1626潮流精选',
    'HEAVENRAVEN',
    '潮研社',
    '潮目',
]

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


def crawler():
    while True:
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
                scrollY = browserdriver.execute_script("return window.scrollY")
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
                    img_element.attrs["src"] = img_element.attrs["data-src"]
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
        article_url = soup.select_one('meta[property="og:url"]').get("content")
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
        session.commit()
    pass


def swipe_down(driver, start_y=0.25, stop_y=0.75, duration=3000):
    #按下手机屏幕，向下滑动
    #注意，向下滑时，x轴不变，要不然就变成了斜向下滑动了
    #@duration：持续时间
    x1 = int(x * 0.5)
    y1 = int(y * start_y)
    x2 = int(x * 0.5)
    y2 = int(y * stop_y)
    # print x1,y1,x2,y2
    driver.swipe(x1, y1, x2, y2, duration)


if __name__ == "__main__":
    threading.Thread(target=crawler).start()

    while True:
        try:
            driver = webdriver.Remote("http://localhost:4723/wd/hub",
                                      desired_caps)
            tabbtnlist = []
            while len(tabbtnlist) == 0:
                tabbtnlist = driver.find_elements_by_id(tabbtnsid)

            for tabbtn in tabbtnlist:
                if tabbtn.text == "通讯录":
                    tabbtn.click()
                    time.sleep(3)
                    top_contact_lines = driver.find_elements_by_id(
                        top_contact_lines_id)
                    for mp_account_line in top_contact_lines:
                        mp_account_line.click()
                        time.sleep(1)
                        while True:
                            mp_account_lines = driver.find_elements_by_id(
                                mp_account_lines_id)
                            if len(mp_account_lines) == 0:
                                break
                            for mp_account_text in mp_account_lines:
                                if mp_account_text.text in mp_account_name_list:
                                    mp_account_text.click()
                                    time.sleep(2)
                                    opbtn = driver.find_element_by_id(
                                        "com.tencent.mm:id/l0")
                                    opbtn.click()
                                    time.sleep(3)
                                    while True:
                                        x = driver.get_window_size()["width"]
                                        y = driver.get_window_size()["height"]
                                        driver.tap([(x * 0.5, y * 0.7),
                                                    (x * 0.5, y * 0.7)], 1000)
                                        time.sleep(10)
                                        opbtn1s = driver.find_elements_by_id(
                                            "com.tencent.mm:id/l0")
                                        if len(opbtn1s) > 1:
                                            driver.swipe(
                                                x * 0.5, 2400, x * 0.5,
                                                2400 - 300, 1000)
                                            continue
                                        else:
                                            opbtn1 = opbtn1s[0]
                                            opbtn1.click()
                                        time.sleep(3)
                                        copybtns = driver.find_elements_by_id(
                                            "com.tencent.mm:id/d0")
                                        copybtnidx = 0
                                        for btn in copybtns:
                                            if btn.text == "复制链接":
                                                btn.click()
                                                time.sleep(1)
                                                r.lpush(
                                                    "link",
                                                    driver.get_clipboard())
                                                break
                                            copybtnidx += 1

                                        driver.back()
                                        time.sleep(3)
                                        driver.swipe(x * 0.5, 2400, x * 0.5,
                                                     2400 - 300, 1000)

                            # account scroll
                            x = driver.get_window_size()["width"]
                            y = driver.get_window_size()["height"]
                            driver.swipe(x * 0.5, 2400, x * 0.5, 2400 - 200,
                                         1000)
                            pass

        except Exception as e:
            continue

        print("end one loop")
        time.sleep(60)
