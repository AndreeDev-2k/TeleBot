#!/bin/bash

# Chạy Telegram bot và poller ở background
nohup python3 src/bot/bot.py > bot.log 2>&1 &
nohup python3 src/poller/poller.py > poller.log 2>&1 &

echo "Bot và Poller đã được khởi động."