import requests
import time
import os
import traceback
import Config
from datetime import datetime

# --- FUNCTIONS ---
def get_price(skin_url, retries=3):
    """Fetch current Steam Market price in Euro, retrying if needed."""
    for attempt in range(retries):
        try:
            response = requests.get(skin_url, timeout=10)
            data = response.json()
            if data.get("success") and data.get("lowest_price"):
                price_str = data["lowest_price"]
                # Clean unwanted symbols
                clean = (
                    price_str.replace("$", "")
                    .replace("€", "")
                    .replace(",", ".")
                    .replace("--", "")
                    .strip()
                )
                try:
                    price = float(clean)
                    # Convert USD → EUR if needed
                    if "$" in price_str:
                        price = round(price * 0.93, 2)
                    return price
                except ValueError:
                    print(f"⚠️ Invalid price format from Steam: '{price_str}' — skipping this check.")
                    return None
            else:
                print(f"⚠️ Attempt {attempt+1}: No valid price, retrying...")
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1}: Error fetching price — {e}")
        time.sleep(2)
    print("❌ Failed to get valid price after retries.")
    return None



def send_ifttt_notification(skin_name, new_price, old_price):
    """Send alert to IFTTT when price changes."""
    data = {
        "value1": f"{skin_name}",
        "value2": f"{new_price} €",
        "value3": f"{old_price} €"
    }
    response = requests.post(Config.IFTTT_URL, json=data)
    if response.status_code == 200:
        print(f"📱 Notification sent for {skin_name}!")
    else:
        print("⚠️ Error sending IFTTT request:", response.status_code)


def log_price_change(skin_name, old_price, new_price):
    """Append a price change entry to the skin's log file."""
    os.makedirs(Config.LOG_FOLDER, exist_ok=True)
    file_name = os.path.join(Config.LOG_FOLDER, f"{skin_name.replace('|', '').replace(' ', '_')}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read last line (if exists)
    last_line = ""
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()

    # Only log if it's a new price
    if not last_line or f"{new_price} €" not in last_line:
        entry = f"{old_price} € ({timestamp}) -> {new_price} € ({timestamp})\n"
        with open(file_name, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"📝 Logged change for {skin_name}: {entry.strip()}")
    else:
        print(f"ℹ️ No change to log for {skin_name}.")

def send_error_notification(error_message):
    """Send an error alert via IFTTT if the script crashes."""
    data = {"value1": "Steam Price Alert Error", "value2": error_message}
    try:
        response = requests.post(Config.IFTTT_URL, json=data)
        if response.status_code == 200:
            print("🚨 Sent crash/error alert to IFTTT!")
        else:
            print(f"⚠️ Failed to send error notification: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Could not send error notification: {e}")

def check_price_change(old_price, new_price, threshold=10):
    """Return True if the price difference is at least `threshold` euros."""
    if old_price is None or new_price is None:
        return False
    return abs(new_price - old_price) >= threshold



# --- MAIN SCRIPT ---
def main():
    print("Fetching initial prices...\n")
    base_prices = {}

    for skin_name, url in Config.SKINS.items():
        price = get_price(url)
        if price:
            base_prices[skin_name] = price
            print(f"✅ {skin_name} starting at {price} €")
        else:
            print(f"⚠️ Could not fetch {skin_name}")

    print("\n--- Monitoring price changes ---\n")

    while True:
        for skin_name, url in Config.SKINS.items():
            current_price = get_price(url)
            if current_price is None:
                print(f"⚠️ Failed to fetch price for {skin_name}")
                continue

            old_price = base_prices.get(skin_name, current_price)
            if current_price != old_price:
                print(f"💹 {skin_name} changed! {old_price} € → {current_price} €")

                # Log every change
                log_price_change(skin_name, old_price, current_price)

                # Notify only if change >= 10€
                if check_price_change(old_price, current_price, threshold=10):
                    send_ifttt_notification(skin_name, current_price, old_price)
                    print(f"🚨 Significant change detected ({abs(current_price - old_price):.2f} € difference)")
                else:
                    print(f"ℹ️ Minor change ({abs(current_price - old_price):.2f} €) — below notification threshold.")

                # Update memory
                base_prices[skin_name] = current_price

            time.sleep(Config.CHECK_INTERVAL)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            error_text = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            print("💥 Program crashed!\n", error_text)
            send_error_notification(error_text[:2000])
            print("🔁 Restarting in 60 seconds...\n")
            time.sleep(60)
