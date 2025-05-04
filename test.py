from bs4 import BeautifulSoup
from src.scraping.base import fetch_html

html_file_path = 'https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd=05&hd=20250429'

html_content = fetch_html(html_file_path)

soup = BeautifulSoup(html_content, 'html.parser')

print(soup.select_one("tr.is-p3-0"))