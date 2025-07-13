python3 -m bot.bot &

until python3 -m poller.poller; do
	 echo "Poller crashed. Restart in 10s"
	 sleep 10
done
>>>>>>> 8e129e5ca34c5dea3caff8ba468e812bcedda12f
