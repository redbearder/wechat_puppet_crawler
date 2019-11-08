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

r = redis.Redis(host='localhost', port=6379, db=0)
engine = create_engine(
    'mysql+pymysql://root@localhost/wechat_puppet_crawler?charset=utf8mb4',
    echo=True)
Session = sessionmaker(bind=engine)

es = Elasticsearch()

desired_caps = {}
desired_caps['appActivity'] = '.ui.LauncherUI'
desired_caps['appPackage'] = 'com.tencent.mm'
desired_caps['automationName'] = 'UiAutomator2'
desired_caps['deviceName'] = '127.0.0.1:7555'
desired_caps['platformName'] = "Android"
desired_caps['platformVersion'] = "6.0.1"
desired_caps['resetKeyboard'] = True
desired_caps['newCommandTimeout'] = "0"
desired_caps['connectHardwareKeyboard'] = True
desired_caps['noReset'] = True

chatlistid = 'com.tencent.mm:id/b9i'
textboxid = 'com.tencent.mm:id/aom'
sendbtnid = 'com.tencent.mm:id/aot'

mp_name_id = 'com.tencent.mm:id/a8p'
mp_name_list = ['央视新闻']

driver = webdriver.Remote('http://localhost:4723/wd/hub', desired_caps)

last_article_title = None

session = Session()


class Article(Base):
    __tablename__ = 'article'

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
                       comment='user create datetime')
    updatedAt = Column(DateTime,
                       default=func.now(),
                       onupdate=func.now(),
                       comment='user update datetime')


def crawler():
    while True:
        l = r.lpop('link')
        if not l:
            time.sleep(3)
            continue
        # crawl l
        o = urlparse(l)
        docid = o.path[3:]
        all_exist_article_list = session.query(Article).filter(
            Article.articleid == docid).all()
        if len(all_exist_article_list) > 0:
            continue
        res = requests.get(l)
        content = res.text

        # xpath
        # selector = etree.HTML(content)
        # links = selector.xpath('//h4/a/text()')
        soup = BeautifulSoup(content, 'html.parser')
        article_title = soup.select_one(
            'meta[property="og:title"]').get('content')
        soup.title.string = article_title
        article_description = soup.select_one(
            'meta[property="og:description"]').get('content')
        article_author = soup.select_one(
            'meta[property="og:article:author"]').get('content')
        article_url = soup.select_one('meta[property="og:url"]').get('content')
        article_image = soup.select_one('meta[property="og:image"]').get(
            'content')
        article_account = soup.select_one('.profile_nickname').string


        imglist = soup.select('img')
        for img_element in imglist:
            if img_element.get('data-src'):
                img_element.attrs['src'] = img_element.attrs['data-src']

        script_list = soup.select('script')
        for script_element in script_list:
            script_element.decompose()

        article_content = soup.prettify()

        es.index(index="article",
                 id=docid,
                 body={
                     "title": article_title,
                     "articleid": docid,
                     "description": article_description,
                     "author": article_author,
                     "url": article_url,
                     "image": article_image,
                     "account": article_account,
                     "content": article_content
                 })

        new_a = Article(title=article_title,
                        articleid=docid,
                        url=article_url,
                        image=article_image,
                        account=article_account,
                        author=article_author,
                        description=article_description)
        session.add(new_a)
        session.commit()
    pass


if __name__ == '__main__':
    threading.Thread(target=crawler).start()

    chatwlist = []
    while len(chatwlist) == 0:
        chatwlist = driver.find_elements_by_id(chatlistid)

    for chatw in chatwlist:
        if chatw.text == '订阅号消息':
            chatw.click()
            time.sleep(3)
            while True:
                try:
                    article_element_list = driver.find_elements_by_id(
                        'com.tencent.mm:id/a9n')
                    # if not last_article_title and len(
                    #         article_element_list) > 0 and article_element_list[
                    #             0].text == last_article_title:
                    #     time.sleep(10)
                    #     continue
                    #     pass
                    # last_article_title = article_element_list[0].text
                    for e in article_element_list:
                        e.click()
                        time.sleep(10)
                        opbtn = driver.find_element_by_id(
                            'com.tencent.mm:id/l0')
                        opbtn.click()
                        time.sleep(3)
                        copybtns = driver.find_elements_by_id(
                            'com.tencent.mm:id/d0')
                        for btn in copybtns:
                            if btn.text == '复制链接':
                                btn.click()
                                time.sleep(1)
                                r.lpush('link', driver.get_clipboard())
                                break

                        backbtn = driver.find_element_by_id(
                            'com.tencent.mm:id/lc')
                        backbtn.click()
                        time.sleep(3)
                        pass
                except Exception as e:
                    continue

    print('in loop')
