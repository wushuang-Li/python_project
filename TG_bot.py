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
MONITORED_WALLETS = ['2gQSss8ur8wWtEo34AYMvwA1GQssYrEhL71J9d5YzTeb'#新的阴谋集团
                     #'BhbnnZRnmdDM5mJ8HPHHVveZwNb2JtECHXiCkW1a1hcE'#自己钱包
                     #'Hw9w3Rf4Q87u1VALwnyxYB6d42ryq7y383P5iWMpxsGX',#新阴谋集团地址
                     #'DYeQjwV8LFkcgcrH4soXkmjZk62MwCZb6g7E5pfev2wj',#老阴谋集团
                     #'9e5r3uhoFoUdVH1yVhAcGqQmzZee9F8QkaX2p9Wt828d',#老阴谋集团
                     #'2wm6N1kL4feGpVHPaCaYb2FJfFoVAdAXuwptexaJuGUb',#老阴谋集团
                     #'49qx9Tr4ZdaRHynutfHd6fgeDiPqiKh6rGnqHabC3ZHi'#老阴谋集团
                     ]
SOL_THRESHOLD = 2  # 设置交易阈值，超过此数值时获取交易信息

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


def get_transaction_details(signature):
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
            if pre_balances[idx] > post_balances[idx]:
                transaction_amount = (pre_balances[idx] - post_balances[idx]) / 10 ** 9
                if transaction_amount > SOL_THRESHOLD:
                    sender = addr
                    receiver = account_keys[1] if account_keys[1] != addr else account_keys[0]
                    break
            elif pre_balances[idx] < post_balances[idx]:  # 接收的情况
                transaction_amount = (post_balances[idx] - pre_balances[idx]) / 10 ** 9
                if transaction_amount > SOL_THRESHOLD:
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
    except TelegramError as e:
        print(f"Error sending message to Telegram: {e}")


async def monitor_wallets():
    last_signatures = {wallet: None for wallet in MONITORED_WALLETS}

    while True:
        for wallet_address in MONITORED_WALLETS:
            try:
                print(f"Checking wallet: {wallet_address}")  # 输出调试信息，确保每次轮询时都检查每个钱包
                latest_signature = get_latest_transaction(wallet_address)

                if latest_signature and latest_signature != last_signatures[wallet_address]:
                    last_signatures[wallet_address] = latest_signature
                    transaction_details = get_transaction_details(latest_signature)

                    if transaction_details:
                        print(f"New transaction detected for {wallet_address}: {transaction_details}")  # 调试输出
                        await send_tg_message(transaction_details)
                    else:
                        print(f"No qualifying transactions detected for {wallet_address}.")
                else:
                    print(f"No new transaction for {wallet_address}.")  # 输出没有新交易的提示

            except Exception as e:
                print(f"Error monitoring {wallet_address}: {e}")

        await asyncio.sleep(10)  # 轮询时间设置为10秒


if __name__ == "__main__":
    asyncio.run(monitor_wallets())
