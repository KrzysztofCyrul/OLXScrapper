import sqlite3
import datetime
import schedule
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Konfiguracja e-maila i bazy danych według oryginalnego skryptu
config = configparser.ConfigParser()
config.read('config.ini')
email_address = config['email']['address']
email_password = config['email']['password']
smtp_server = "smtp.gmail.com"
smtp_port = 587

conn = sqlite3.connect('olx_auctions.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS auctions
             (date text, title text, link text UNIQUE)''')

is_full_scan_day = True

def fetch_and_update_selenium():
    global is_full_scan_day
    new_auctions = []

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('log-level=3')  # Wykluczenie logowania

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        for base_url in base_urls:
            page_number = 1
            max_page_number = 1 if not is_full_scan_day else float('inf')  # Dostosowanie do is_full_scan_day

            while page_number <= max_page_number:
                if page_number == 1:
                    print(f"Skanowanie strony 1 dla URL: {base_url}")
                url = base_url.format(page_number)
                driver.get(url)
                time.sleep(2)  # Daj czas na załadowanie strony

                if page_number == 1 and is_full_scan_day:
                    pagination_elements = driver.find_elements(By.CLASS_NAME, "css-1mi714g")
                    if pagination_elements:
                        max_page_numbers = [int(elem.text) for elem in pagination_elements if elem.text.isdigit()]
                        max_page_number = max(max_page_numbers) if max_page_numbers else 1

                elements = driver.find_elements(By.CLASS_NAME, "css-u2ayx9")
                location_date_elements = driver.find_elements(By.CSS_SELECTOR, 'p[data-testid="location-date"]')
                links = driver.find_elements(By.CLASS_NAME, "css-rc5s2u")

                for i, elem in enumerate(elements):
                    try:
                        title = elem.text + " " + location_date_elements[i].text
                        link = "https://www.olx.pl" + links[i].get_attribute('href')
                        # Sprawdzenie, czy aukcja już istnieje w bazie i dodawanie nowej aukcji
                        c.execute('SELECT * FROM auctions WHERE link=?', (link,))
                        if c.fetchone() is None:
                            c.execute('INSERT INTO auctions (date, title, link) VALUES (?, ?, ?)',
                                      (datetime.datetime.now().isoformat(), title, link))
                            conn.commit()
                            new_auctions.append((datetime.datetime.now().isoformat(), title, link))
                            print(f"Znaleziono nową aukcję: {title}")
                    except IndexError:
                        print("Error processing an auction. Skipping.")
                        continue

                if page_number >= max_page_number:
                    print(f"Finished scanning all pages up to {max_page_number} for URL: {base_url}")
                    break
                page_number += 1
                print(f"Przechodzenie do strony numer {page_number} dla URL: {base_url}")

    finally:
        driver.quit()

    if new_auctions:
        send_email(new_auctions, "Nowa aukcja zneleziona!")

def send_email(auctions, subject):
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = email_address
    msg['Subject'] = subject

    body = "Ostatnie aukcje:\n\n"
    for auction in auctions:
        body += f"{auction[1]}\nLink: {auction[2]}\n\n"

    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(email_address, email_password)
    text = msg.as_string()
    server.sendmail(email_address, email_address, text)
    server.quit()

def reset_full_scan():
    global is_full_scan_day
    is_full_scan_day = True
    print("Full scan mode.")

def set_to_shallow_scan():
    global is_full_scan_day
    is_full_scan_day = False
    print("Set to shallow scan mode.")

def send_daily():
    c.execute('SELECT * FROM auctions')
    auctions = c.fetchall()
    if auctions:
        send_email(auctions, "Daily auction summary")
        print("Email sent with daily auction summary!")

# Definiowanie URLi bazowych
base_urls = [
    "https://www.olx.pl/motoryzacja/samochody/podkarpackie/?page={}&search%5Bfilter_float_price%3Ato%5D=5000&search%5Border%5D=created_at%3Adesc",
    "https://www.olx.pl/motoryzacja/samochody/podkarpackie/?page={}&search%5Border%5D=created_at:desc&search%5Bfilter_float_price:to%5D=10000&search%5Bfilter_enum_condition%5D%5B0%5D=damaged",
    # Twoje URL-e
]

start_time = datetime.datetime.now()
first_task_time = (start_time + datetime.timedelta(minutes=1)).strftime('%H:%M')
second_task_time = (start_time + datetime.timedelta(minutes=3)).strftime('%H:%M')

# Planowanie zadań
schedule.every().day.at(first_task_time).do(send_daily).do(reset_full_scan)
schedule.every().day.at(second_task_time).do(set_to_shallow_scan)
schedule.every(30).seconds.do(fetch_and_update_selenium)

while True:
    schedule.run_pending()
    time.sleep(1)
