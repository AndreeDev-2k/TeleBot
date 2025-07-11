#!/bin/bash

cd /app/src

# Chạy Telegram bot và poller ở background
python3 -m bot.bot &
python3 -m poller.poller &
wait

echo "Bot và Poller đã được khởi động."
