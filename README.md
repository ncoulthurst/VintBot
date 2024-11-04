# VintBot
A monitoring tool which fetches the newest items uploaded to the Vinted marketplace and sends them to a discord server.

## Prerequisites
- **Python 3.x**
- **PyVinted Library**
- **Requests Library**



Replace the item.py file in the PyVinted library with the one provided in this repository.
Replace the Rapid API keys & discord bot token inside main.py with your own.
Replace the channel ID's within the brand_channels.json with your own discord channel IDs.


$ git clone https://github.com/ncoulthurst/VintBot.git
$ cd Vinted-webhook\bot
$ pip install -r requirements.txt

$ python main.py

Rapid API keys can be obtained here:
https://rapidapi.com/MarketplaceAPIs/api/vinted6
