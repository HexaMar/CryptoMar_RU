#Основной скрипт для брутфорса с помощью CryptoMar
import time
import os
import re
import hashlib
from datetime import datetime

from tqdm import tqdm
from multiprocessing import Process, Value, shared_memory, Manager
import CryptoMar
import requests
import bech32

# === CONFIG ===
FILE_PATH = 'P2WPKH.nonzero.txt'
BLOCKSTREAM_API = 'https://blockstream.info/api/address/'
num_processes = os.cpu_count()*2
BLOCKCHAIN_EXPLORER = "https://www.blockchain.com/btc/address/"


def get_valid_user_wallet():
    print_banner()
    if load_user_wallet() == False:
        print('|  Для запуска необходимо ввести адрес вашего Bitcoin кошелька        |')
        print('|  Когда программа найдет доступные средства,                         |')
        print('|  они будут автоматически переведены на ваш кошелек.                 |')
        print('|=====================================================================|')

        while True:
            user_wallet = input("|  Введите адрес вашего кошелька:").strip()
            if check_user_wallet(user_wallet):
                balance = check_balance(user_wallet)
                print(f"|-----------------------Загрузка вашего кошелька----------------------|")
                print(f"|  Кошелек:                                                           |")
                print(f"|  {user_wallet}{' ' * (67 - len(user_wallet))}|")
                print(f"|  Валиден.                                                           |")
                print(f"|  Баланс: {balance} сатоши.{' ' * (70 - len(f'|  Баланс: {balance} сатоши.'))}|")
                print(f"|  Проверить в блокчейн:                                              |")
                print(f"|  {BLOCKCHAIN_EXPLORER}{user_wallet}")
                print(f"|---------------------------------------------------------------------|")
                return user_wallet
            else:
                print("|  Попробуйте снова.                                                  |\n"
                      "|---------------------------------------------------------------------|")
    else:
        load, user_wallet = load_user_wallet()
        balance = check_balance(user_wallet)
        print(f"|-----------------------Загрузка вашего кошелька----------------------|")
        print(f"|  Кошелек:                                                           |")
        print(f"|  {user_wallet}{' ' * (67 - len(user_wallet))}|")
        print(f"|  Валиден.                                                           |")
        print(f"|  Баланс: {balance} сатоши.{' ' * (70 - len(f'|  Баланс: {balance} сатоши.'))}|")
        print(f"|  Проверить в блокчейн:                                              |")
        print(f"|  {BLOCKCHAIN_EXPLORER}{user_wallet}")
        print(f"|---------------------------------------------------------------------|")
        return user_wallet


def check_user_wallet(user_wallet):
    if user_wallet.startswith("1") or user_wallet.startswith("3"):
        save_user_wallet(user_wallet)
        return validate_legacy_address(user_wallet)

    if user_wallet.lower().startswith("bc1"):
        save_user_wallet(user_wallet)
        return validate_bech32_address(user_wallet)

    print("❌ Неверный адрес Bitcoin кошелька (Неизвестный формат).")
    return False


def validate_legacy_address(address):
    if not re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
        return False

    base58_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = 0
    for char in address:
        value = value * 58 + base58_chars.index(char)

    address_bytes = value.to_bytes(25, 'big')

    checksum = address_bytes[-4:]
    hash_checksum = hashlib.sha256(hashlib.sha256(address_bytes[:-4]).digest()).digest()[:4]

    if checksum == hash_checksum:
        return True
    else:
        print("❌ Неверная контрольная сумма Legacy адреса.")
        return False


def validate_bech32_address(address):
    try:
        hrp, data = bech32.bech32_decode(address)
        if not hrp or not data:
            print("❌ Неверный формат Bech32.")
            return False

        if hrp not in ["bc"]:
            print("❌ Неверный Bech32 HRP (должен быть 'bc').")
            return False

        reconstructed = bech32.bech32_encode(hrp, data)
        if reconstructed.lower() == address.lower():
            return True
        else:
            print("❌ Неверная контрольная сумма Bech32.")
            return False
    except Exception as e:
        print(f"❌ Ошибка валидации Bech32: {e}")
        return False


def save_user_wallet(user_wallet):
    file_path = "user_wallet.txt"

    try:
        with open(file_path, "w") as file:
            file.write(f"{user_wallet}\n")
    except Exception as e:
        print(f"❌ Ошибка сохранения адреса кошелька: {e}")


def load_user_wallet():
    file_path = "user_wallet.txt"
    try:
        with open(file_path, "r") as file:
            saved_wallet = file.read().strip()

            if check_user_wallet(saved_wallet):
                return True, saved_wallet
            else:
                return False
    except FileNotFoundError:
        return False


def print_banner():
    print(f""" _____________________________________________________________________
|========================= Добро пожаловать в ========================|
|                              ᴄʀʏᴘᴛᴏᴍᴀʀ                              |
|============================== Версия 1.0 ===========================|
|                                                                     |""")
    d = f"|  Курс: 1 BTC = {get_bitcoin_price()} USD ({datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')})"
    print(f"{d}{' ' * (70 - len(d))}|")


def print_running_banner():
    space = 67 - len(user_wallet)
    spacer = space*" "
    space2 = 70 - len(f"|  Баланс: {check_balance(user_wallet)//100000000} BTC \ {check_balance(user_wallet)//int(get_bitcoin_price())} USD.")
    spacer2 = space2*" "
    print(f"""|  Адрес реципиент:                                                   |
|  {user_wallet}{spacer}|
|  Баланс: {check_balance(user_wallet)//100000000} BTC \ {check_balance(user_wallet)//get_bitcoin_price()} USD.{spacer2}|
|============================ В процессе =============================|
|                              ᴄʀʏᴘᴛᴏᴍᴀʀ                              |
|============================ Версия 1.0 =============================|""")

def load_addresses():
    with open(FILE_PATH, 'r') as f:
        addresses = {line.split()[0] for line in f}
    return addresses

def save_found_keys(priv_key, wif, address, balance):
    with open("/Volumes/BitcoinDrive/found_keys.txt", "a") as f:
        f.write(f"Private Key: {priv_key}\nWIF: {wif}\nAddress: {address}\nBalance: {balance} satoshis\n\n")

def check_balance(address):
    try:
        response = requests.get(f'{BLOCKSTREAM_API}{address}')
        if response.status_code == 200:
            data = response.json()
            balance = data.get('chain_stats', {}).get('funded_txo_sum', 0) - data.get('chain_stats', {}).get('spent_txo_sum', 0)
            return balance
    except Exception as e:
        print(f'❌ Ошибка получения баланса {address}: {e}')
    return 0


def get_bitcoin_price():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
        data = response.json()
        price = data['bitcoin']['usd']
        return price
    except Exception as e:
        return 100000

def worker(counter, found, address_shm_name, address_size):
    existing_shm = shared_memory.SharedMemory(name=address_shm_name)
    address_bytes = existing_shm.buf[:address_size]
    address_set = set(address_bytes.tobytes().decode().splitlines())

    local_counter = 0
    while not found.value:
        priv_key = CryptoMar.get_priv_key()
        adress = CryptoMar.get_bech32(priv_key)

        if adress in address_set:
            found.value = True
            wif, _ = CryptoMar.get_wif(priv_key)
            balance = check_balance(adress)
            massage = f"\n|============================== НАЙДЕНО ==============================|\n|------------------------------- АДРЕС -------------------------------|\n{adress}\n|------------------------------- БАЛАНС ------------------------------|\n{balance} сатоши.\n|-------------------------------- WIF --------------------------------|\n{wif}\n|=====================================================================|"
            print(massage)
            return

        local_counter += 1

        if local_counter >= 15234:
            with counter.get_lock():
                counter.value += local_counter
            local_counter = 0

    with counter.get_lock():
        counter.value += local_counter


if __name__ == '__main__':
    counter = Value('i', 0, lock=True)
    found = Value('b', False)
    start_time = time.time()

    user_wallet = get_valid_user_wallet()
    if check_user_wallet(user_wallet) == False:
        user_wallet = get_valid_user_wallet()

    print("|  Настройка завершена.                                               |")
    print("|  Пожалуйста, подождите, процесс скоро начнется...                   |")
    print("|----------------------Загрузка адресов в память----------------------|")
    address_set = load_addresses()
    e = f"|  Загружено {len(address_set)} адресов."
    print(f"{e}{' '*(70-len(e))}|")
    print(f"|---------------------------------------------------------------------|")
    print_running_banner()

    print("""|  Процесс поиска ключей не является быстрым.                         |
|  Это вопрос дней или даже недель, а не часов.                       |
|  Все зависит от мощности вашего процессора и удачи.                 |
|_____________________________________________________________________|
|                                                                     |""")

    address_str = '\n'.join(address_set)
    address_bytes = address_str.encode()
    shm = shared_memory.SharedMemory(create=True, size=len(address_bytes))
    shm.buf[:len(address_bytes)] = address_bytes

    processes = [
        Process(target=worker, args=(counter, found, shm.name, len(address_bytes)))
        for _ in range(num_processes)
    ]

    for p in processes:
        p.start()

    with tqdm(
            total=0,
            unit=' addresses',
            dynamic_ncols=False,
            bar_format="| {rate_fmt:<30}   Total: {n:<27} |".ljust(70),
            position=0,
            leave=True
    ) as pbar:
        while not found.value:
            with counter.get_lock():
                counter.value += 1234

            pbar.n = counter.value
            pbar.refresh()



    for p in processes:
        p.join()

    shm.close()
    shm.unlink()

    total_time = time.time() - start_time
    print(f"\nВсего обработано: {counter.value} адресов")
    print(f"Средняя скорость: {counter.value / total_time:.2f} адресов/с")
