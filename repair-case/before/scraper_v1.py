"""
scraper_v1.py

books.toscrape.com のトップページから書籍情報(タイトル/価格/評価/在庫)を
取得して CSV に書き出す……はずのスクレイパー。

作成: 2024年頃 (社内の別担当者がAIに書かせたまま放置)
"""

import requests
from bs4 import BeautifulSoup
import csv

BASE_URL = "https://books.toscrape.com/"


def scrape_page(url):
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    books = []
    for pod in soup.select("article.product_pod"):
        title = pod.select_one("h3 a")["title"]

        # 価格は p.price の中の .price_color に入っている想定
        price = pod.select_one("p.price .price_color").text

        # 在庫バッジは .stock-badge クラスに入っている想定
        stock = pod.select_one(".stock-badge").text.strip()

        books.append({"title": title, "price": price, "stock": stock})

    return books


def main():
    print(f"Scraping {BASE_URL} ...")
    books = scrape_page(BASE_URL)
    print(f"Got {len(books)} books")

    with open("books.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price", "stock"])
        writer.writeheader()
        writer.writerows(books)

    print("Done -> books.csv")


if __name__ == "__main__":
    main()
