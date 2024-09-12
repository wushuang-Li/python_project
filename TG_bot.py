import requests
import json
from datetime import datetime, timedelta
import asyncio
from telegram import Bot
from telegram.error import TelegramError

# Telegram Bot and Chat Info
TG_BOT_TOKEN = '7488495204:AAHz7WCyiWvqCsWqbVt07GwwOzWH6VLSVyE'
TG_CHAT_ID = '1124778633'
bot = Bot(token=TG_BOT_TOKEN)

SOLANA_RPC_URL = 'https://api.mainnet-beta.solana.com'

# 针对不同钱包设定不同的阈值
MONITORED_WALLETS = {
    '2gQSss8ur8wWtEo34AYMvwA1GQssYrEhL71J9d5YzTeb': 2,  # 钱包1，阈值为 2 SOL
    'BhbnnZRnmdDM5mJ8HPHHVveZwNb2JtECHXiCkW1a1hcE': 0.1   # 钱包2，阈值为 5 SOL
}

def get_latest_transaction(wallet_address):
    headers = {
        'Content-Type': 'application/json'
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getConfirmedSignaturesForAddress2",
        "params": [wallet_address, {"limit": 1}]
    }

    try:
        response = requests.post(SOLANA_RPC_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching latest transaction for {wallet_address}: {e}")
        return None

    transactions = result.get('result', [])
    if not transactions:
        return None

    latest_signature = transactions[0]['signature']
    return latest_signature


def get_transaction_details(signature, wallet_address):
    headers = {
        'Content-Type': 'application/json'
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getConfirmedTransaction",
        "params": [signature]
    }

    try:
        response = requests.post(SOLANA_RPC_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching transaction details for {signature}: {e}")
        return None

    transaction = result.get('result', {})
    if not transaction:
        return None

    block_time = transaction.get('blockTime')
    if block_time:
        block_time = datetime.utcfromtimestamp(block_time) + timedelta(hours=8)
        block_time = block_time.strftime('%Y-%m-%d %H:%M:%S')

    meta = transaction.get('meta', {})
    pre_balances = meta.get('preBalances', [])
    post_balances = meta.get('postBalances', [])

    account_keys = transaction.get('transaction', {}).get('message', {}).get('accountKeys', [])

    sender = None
    receiver = None
    transaction_amount = None
    for idx, addr in enumerate(account_keys):
        if addr in MONITORED_WALLETS:
            # 根据钱包地址获取其阈值
            threshold = MONITORED_WALLETS[wallet_address]
            if pre_balances[idx] > post_balances[idx]:
                transaction_amount = (pre_balances[idx] - post_balances[idx]) / 10 ** 9
                if transaction_amount > threshold:
                    sender = addr
                    receiver = account_keys[1] if account_keys[1] != addr else account_keys[0]
                    break
            elif pre_balances[idx] < post_balances[idx]:
                transaction_amount = (post_balances[idx] - pre_balances[idx]) / 10 ** 9
                if transaction_amount > threshold:
                    receiver = addr
                    sender = account_keys[1] if account_keys[1] != addr else account_keys[0]
                    break

    if sender and receiver and transaction_amount:
        return {
            'signature': signature,
            'time': block_time,
            'transaction_amount': transaction_amount,
            'sender_address': sender,
            'receiver_address': receiver
        }
    else:
        return None


async def send_tg_message(transaction_details):
    message = (
        f"新交易数据:\n"
        f"交易签名: {transaction_details['signature']}\n"
        f"交易时间: {transaction_details['time']} (UTC+8)\n"
        f"交易SOL数量: {transaction_details['transaction_amount']} SOL\n"
        f"发送地址: {transaction_details['sender_address']}\n"
        f"接受地址: {transaction_details['receiver_address']}"
    )

    try:
        await bot.send_message(chat_id=TG_CHAT_ID, text=message)
        await asyncio.sleep(0.5)  # 每次发送消息后等待 0.5 秒，避免并发过多
    except TelegramError as e:
        print(f"Error sending message to Telegram: {e}")


async def monitor_wallets():
    last_signatures = {wallet: None for wallet in MONITORED_WALLETS}

    while True:
        for wallet_address in MONITORED_WALLETS:
            try:
                print(f"Checking wallet: {wallet_address}")
                latest_signature = get_latest_transaction(wallet_address)

                if latest_signature and latest_signature != last_signatures[wallet_address]:
                    last_signatures[wallet_address] = latest_signature
                    transaction_details = get_transaction_details(latest_signature, wallet_address)

                    if transaction_details:
                        print(f"New transaction detected for {wallet_address}: {transaction_details}")
                        await send_tg_message(transaction_details)
                    else:
                        print(f"No qualifying transactions detected for {wallet_address}.")
                else:
                    print(f"No new transaction for {wallet_address}.")

            except Exception as e:
                print(f"Error monitoring {wallet_address}: {e}")

        await asyncio.sleep(10)  # 轮询间隔时间为10秒


if __name__ == "__main__":
    asyncio.run(monitor_wallets())
