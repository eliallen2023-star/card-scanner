"""Push alerts to your phone with ntfy (free app for iPhone and Android)."""
import requests


def send(topic, title, body, url, image=None, dry_run=False):
    if dry_run or not topic:
        print(f"\n--- ALERT ---\n{title}\n{body}\n{url}")
        return
    headers = {"Title": title.encode("utf-8"), "Click": url, "Tags": "baseball",
               "Actions": f"view, Open on eBay, {url}"}
    if image:
        headers["Attach"] = image
    requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                  headers=headers, timeout=20).raise_for_status()
