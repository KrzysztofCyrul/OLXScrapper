import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import schedule
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import configparser


config = configparser.ConfigParser()
config.read('config.ini')

# Konfiguracja e-maila
email_address = config['email']['address']  # Zmień na swój adres e-mail
email_password = config['email']['password']  # Zmień na swoje hasło
print(email_address + " " + email_password)
smtp_server = "smtp.gmail.com"  # Zmień na serwer SMTP swojego dostawcy
smtp_port = 587  # Zmień na port SMTP swojego dostawcy

# Połączenie z bazą danych SQLite
conn = sqlite3.connect('olx_auctions.db')
c = conn.cursor()

# Utworzenie tabeli, jeśli nie istnieje
c.execute('''CREATE TABLE IF NOT EXISTS auctions
             (date text, title text, link text UNIQUE)''')


# Zmienna globalna do śledzenia trybu przeszukiwania
is_full_scan_day = True

def fetch_and_update():
    global is_full_scan_day
    base_url = "https://www.olx.pl/motoryzacja/samochody/podkarpackie/?page={}&search%5Bfilter_float_price%3Ato%5D=5000&search%5Border%5D=created_at%3Adesc"
    page_number = 1

    # Jeśli nie jest pełne skanowanie, sprawdź tylko pierwszą stronę
    max_page_number = 1 if not is_full_scan_day else float('inf')

    while page_number <= max_page_number:
        if page_number == 1:
            print("Skanowanie strony 1")
        url = base_url.format(page_number)
        response = requests.get(url)
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")
        elements = soup.find_all(class_="css-u2ayx9")
        location_date_elements = soup.select('p[data-testid="location-date"]')
        links = soup.find_all(class_="css-rc5s2u")

        if not elements or page_number == max_page_number:
            break

        for i in range(len(elements)):
            title = elements[i].text + " " + location_date_elements[i].text
            link = "https://www.olx.pl" + links[i].get('href')
            c.execute('SELECT * FROM auctions WHERE link=?', (link,))
            if c.fetchone() is None:
                print("Znaleziono nową aukcję: {}".format(title))
                c.execute('INSERT INTO auctions (date, title, link) VALUES (?, ?, ?)', (datetime.now().isoformat(), title, link))
                # Wysłanie e-maila z nową aukcją
                send_email([(datetime.now().isoformat(), title, link)], "Nowa aukcja: {}".format(title))
                conn.commit()
                print("Zmiany w bazie danych zostały zatwierdzone.")

        if is_full_scan_day:
            # Aktualizacja max_page_number po przetworzeniu pierwszej strony
            if page_number == 1:
                pagination_elements = soup.find_all(class_="css-1mi714g")
                max_page_numbers = [int(elem.text) for elem in pagination_elements if elem.text.isdigit()]
                max_page_number = max(max_page_numbers) if max_page_numbers else 1

        page_number += 1
        if page_number > max_page_number:
            print("Osiągnięto maksymalny numer strony, kończenie...")
            break
        else:
            print("Przechodzenie do strony numer {}".format(page_number))

def reset_full_scan():
    global is_full_scan_day
    is_full_scan_day = True
    print("Zresetowano tryb pełnego skanowania.")

def set_to_shallow_scan():
    global is_full_scan_day
    is_full_scan_day = False
    print("Ustawiono tryb płytkiego skanowania.")


def send_daily():
    c.execute('SELECT * FROM auctions')
    auctions = c.fetchall()
    if auctions:
        send_email(auctions, "Codzienne podsumowanie aukcji")
        print("Wysłano e-mail z codziennym podsumowaniem aukcji!")

def send_email(auctions, subject):
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = email_address  # Wysyła do samego siebie jako przykład
    msg['Subject'] = subject

    body = "Oto najnowsze aukcje:\n\n"
    for auction in auctions:
        body += f"{auction[1]}\nLink: {auction[2]}\n\n"

    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(email_address, email_password)
    text = msg.as_string()
    server.sendmail(email_address, email_address, text)
    server.quit()

# Planowanie zadań
schedule.every().day.at("08:08").do(send_daily).do(reset_full_scan)
schedule.every().day.at("08:09").do(set_to_shallow_scan)
schedule.every(1).minutes.do(fetch_and_update)

while True:
    schedule.run_pending()
    time.sleep(1)
