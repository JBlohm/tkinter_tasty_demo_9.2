"""
This is an application which utilizes asyncio and tkinter to display
candles from DXLinkStreamer provided via tastytrade api.
Requires tastytrade-9.2 due to breaking changes in naming convention and
in optionality in fields (open/high/low/close) from 9.2 to 9.3 leading to missing eventFlags from some candles.

pip install tastytrade==9.2
"""

# pylint: disable=line-too-long

import tkinter as tk
from tkinter import ttk
import asyncio
import json

from datetime import datetime
import pandas as pd

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf

from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Candle
from tastytrade import Session

#import logging
#logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

TX_PENDING = 0x1
REMOVE_EVENT = 0x2
SNAPSHOT_BEGIN = 0x4
SNAPSHOT_END = 0x8
SNAPSHOT_SNIP = 0x10
SNAPSHOT_MODE = 0x40

def check_candle_event_flags(candle):
    """
    Checks the candle eventFlags and prints each active flag (used mainly for debugging purpose)
    """
    if (candle.eventFlags & TX_PENDING) != 0:
        print('TX_PENDING')
    if (candle.eventFlags & REMOVE_EVENT) != 0:
        print('REMOVE_EVENT')
    if (candle.eventFlags & SNAPSHOT_BEGIN) != 0:
        print('SNAPSHOT_BEGIN')
    if (candle.eventFlags & SNAPSHOT_END) != 0:
        print('SNAPSHOT_END')
    if (candle.eventFlags & SNAPSHOT_SNIP) != 0:
        print('SNAPSHOT_SNIP')
    if (candle.eventFlags & SNAPSHOT_MODE) != 0:
        print('SNAPSHOT_MODE')


# I do not like any of the default styles, so here is a custom style
binance_dark = {
    "base_mpl_style": "dark_background",
    "marketcolors": {
        "candle": {"up": "#3dc985", "down": "#ef4f60"},  
        "edge": {"up": "#3dc985", "down": "#ef4f60"},  
        "wick": {"up": "#3dc985", "down": "#ef4f60"},  
        "ohlc": {"up": "green", "down": "red"},
        "volume": {"up": "#247252", "down": "#82333f"},  
        "vcedge": {"up": "green", "down": "red"},  
        "vcdopcod": False,
        "alpha": 1,
    },
    "mavcolors": ("#ad7739", "#a63ab2", "#62b8ba"),
    "facecolor": "#1b1f24",
    "gridcolor": "#2c2e31",
    "gridstyle": "--",
    "y_on_right": False,
    "rc": {
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.edgecolor": "#474d56",
        "axes.titlecolor": "red",
        "figure.facecolor": "#161a1e",
        "figure.titlesize": "x-large",
        "figure.titleweight": "semibold",
        'axes.labelsize': 6,   # Font size for axis labels
        'xtick.labelsize': 6,   # Font size for x-axis tick labels
        'ytick.labelsize': 6,   # Font size for y-axis tick labels
        'font.size': 6         # Base font size
    },
    "base_mpf_style": "binance-dark",
}


def candle_to_dataframe(candle):
    """ Assuming 'candle' is your Candle object, function to convert a single Candle to DataFrame"""
    try:
        data_row = {
            'eventSymbol': candle.eventSymbol,
            'eventTime': candle.eventTime,
            'eventFlags': candle.eventFlags,
            'index': candle.index,
            'time': datetime.fromtimestamp(candle.time / 1000),  # Convert to datetime
            'sequence': candle.sequence,
            'count': candle.count,
            'open': float(candle.open),
            'high': float(candle.high),
            'low': float(candle.low),
            'close': float(candle.close),
            'volume': float(candle.volume),
            'vwap': float(candle.vwap),
            'bidVolume': float(candle.bidVolume) if candle.bidVolume is not None else None,
            'askVolume': float(candle.askVolume) if candle.askVolume is not None else None,
            'impVolatility': float(candle.impVolatility) if candle.impVolatility is not None else None,
            'openInterest': candle.openInterest
        }
        df = pd.DataFrame([data_row])
    except: # pylint: disable=bare-except
        print("EXCEPT: candle_to_dataframe")
        print(candle)
        df = pd.DataFrame()

    return df


def vwap(df):
    """ calculate periodic (start of dataset) volume weighted average price """
    q = df.volume.values
    p = df.vwap.values
    return df.assign(periodic_vwap=(p * q).cumsum() / q.cumsum())


def read_config():
    """
    Reads the username and password from config.json and returns them.
    ToDo: Replace with encryped version, before production use. (This here is NOT safe to use, this is readable DEV stuff..)
    """
    try:
        with open('tasty_tools_config.json', 'r', encoding="utf-8") as f:
            config = json.load(f)
            username = config.get('username')
            password = config.get('password')
            return username, password
    except FileNotFoundError:
        print("Config file not found.")
        return None, None
    except json.JSONDecodeError:
        print("Error decoding JSON from the config file.")
        return None, None


class App:
    """Main application class"""
    async def exec(self):
        """Run the application"""
        self.window = Window(asyncio.get_event_loop()) # pylint: disable=attribute-defined-outside-init
        await self.window.display()


class Window(tk.Tk):
    """Main Tk Window class, containing most of the functions to run the application"""
    def __init__(self, loop):
        super().__init__()
        # Sample initial data
        self.disp_df = pd.DataFrame({
            'open': [0],
            'high': [1],
            'low': [0],
            'close': [1],
            'volume': [1]
        }, index=pd.to_datetime(['2024-01-01']))
        self.loop = loop
        self.run = True
        self.animation = "░▒▒▒▒▒"
        self.title('DXLinkStreamer')
        #self.iconbitmap('./assets/pythontutorial.ico') # 150x150 icon file

        self.label_quote = ttk.Label(text="----.--", font=("Helvetica", 20), foreground="")
        self.label_quote.grid(row=0, column=0, padx=(8, 8), pady=(8, 8))
        self.label_vwap = ttk.Label(text="----.--", font=("Helvetica", 20), foreground="")
        self.label_vwap.grid(row=0, column=1, sticky="e", padx=(8, 8), pady=(8, 8))

        self.fig, self.axlist = mpf.plot(
            self.disp_df,
            type='candle',
            style=binance_dark,
            columns=["open", "high", "low", "close", "volume"],
            volume=True,
            ylabel="Price ($)",
            ylabel_lower="Volume",
            returnfig=True,
            scale_padding={'left': 0.75, 'top': 0.25, 'right': 0.25, 'bottom': 0.75},

        )
        self.ax = self.axlist[0]  # Main plot axis

        # Embed the mplfinance chart in the Tkinter window
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, columnspan=2, sticky="nsew")
        self.canvas_widget.config(width=800, height=600)

        self.label = tk.Label(text="")
        self.label.grid(row=2, columnspan=2, padx=(8, 8), pady=(4, 8))
        button_quit = tk.Button(text="Quit", width=10, command=self.quit)
        button_quit.grid(row=2, column=1, sticky="nse", padx=8, pady=(4, 8))

        self.update()


    async def animation_async(self):
        """async demo text animation"""
        while self.run:
            self.label["text"] = self.animation
            self.animation = self.animation[1:] + self.animation[0]
            self.update()
            await asyncio.sleep(.1)


    async def get_candle_async(self):
        """get candle from DXLinkStreamer and display graphic"""
        async with DXLinkStreamer(session) as streamer:
            subs_list = ['SPY']  # list of symbols to subscribe to ['SPY','/ES:XCME','GDX']
            #epoch = datetime(2024, 12, 6, 0, 0, 0)
            # Get today's date at midnight
            epoch = datetime.combine(datetime.today().date(), datetime.min.time())
            #print(epoch.isoformat())

            await streamer.subscribe_candle(symbols=subs_list, interval="5m", start_time = epoch, extended_trading_hours=False)

            df = pd.DataFrame()
            update_graph = False

            while self.run:
                try:
                    candle = await asyncio.wait_for(streamer.get_event(Candle), timeout=2.0)
                    #print(candle)
                    #check_candle_event_flags(candle)

                    if (candle.eventFlags & SNAPSHOT_BEGIN) != 0:
                        update_graph = False

                    if (candle.eventFlags & SNAPSHOT_END) != 0:
                        update_graph = True

                    if (candle.eventFlags & REMOVE_EVENT) == 0: # if this is not a remove event, process the candle
                        df_new = candle_to_dataframe(candle)
                        if not df_new.empty:
                            df = pd.concat([df, df_new], axis=0, ignore_index=True)
                            df.drop_duplicates(subset=['time'], keep='last', inplace=True)
                            df.sort_values(by=['time'], inplace=True)

                    if update_graph & (not df.empty):
                        self.disp_df = df.copy(deep=True)
                        self.disp_df.set_index('time', inplace=True)

                        # Clear the axes
                        self.ax.clear()
                        if len(self.axlist) > 2:
                            volume_ax = self.axlist[2]
                            volume_ax.clear()
                        else:
                            volume_ax = None

                        #volume weighted average price (vwap)
                        self.disp_df = vwap(self.disp_df)
                        disp_vwap = mpf.make_addplot(self.disp_df['periodic_vwap'], type='line', ax=self.ax, color='cyan', width=1, label="vwap")

                        mpf.plot(
                            self.disp_df,
                            type='candle',
                            style=binance_dark,
                            ax=self.ax,
                            volume=volume_ax,
                            columns=["open", "high", "low", "close", "volume"],
                            ylabel="Price ($)",
                            ylabel_lower="Volume",  addplot=disp_vwap, #update_width_config=dict(candle_linewidth=0.5, candle_width=0.5),
                        )

                        self.canvas.draw()

                        # use last row of dataframe to get close and periodic_vwap of the most recent candle, float with 2 decimal places
                        self.label_quote["text"] = f"{candle.eventSymbol} {self.disp_df['close'].iat[-1]:.2f}"
                        self.label_vwap["text"] = f"vwap {self.disp_df['periodic_vwap'].iat[-1]:.2f}"

                        self.update()

                    await asyncio.sleep(0)
                except TimeoutError:
                    #print("DEBUG: get_event(Candle) : timeout")
                    await asyncio.sleep(0)

            await streamer.close()


    def quit(self):
        self.run = False


    async def display(self):
        """async main loop"""
        while self.run:
            await asyncio.gather(
                self.animation_async(),
                self.get_candle_async(),
            )

# Disabled for demo purpose

#user_config = read_config()
#session = Session(user_config[0], user_config[1]) # username, password

# This is for demo purpose only!! NEVER store username/password in sourcecode! Else they might end up on Github :-(
session = Session('your_TTuser_name', 'your_TTpassword') # username, password

asyncio.run(App().exec())
