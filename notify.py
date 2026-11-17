"""Push alerts to your phone with ntfy (free app for iPhone and Android)."""
import requests


def rating_buttons(feedback_topic, item_id):
    """Good / Medium / Bad buttons on the alert. Tapping one sends your rating to the
    ratings topic (no app needed); the next scan learns from it. ntfy allows 3 buttons,
    so tapping the alert itself opens the listing on eBay."""
    return "; ".join(
        f"http, {name}, https://ntfy.sh/{feedback_topic}, method=POST, "
        f"body='{label} {item_id}', clear=true"
        for name, label in (("Good", "good"), ("Medium", "medium"), ("Bad", "bad")))


def send(topic, title, body, url, image=None, dry_run=False, feedback_topic=None, item_id=None):
    if dry_run or not topic:
        print(f"\n--- ALERT ---\n{title}\n{body}\n{url}")
        return
    headers = {"Title": title.encode("utf-8"), "Click": url, "Tags": "baseball"}
    if feedback_topic and item_id:
        headers["Actions"] = rating_buttons(feedback_topic, item_id)
    else:
        headers["Actions"] = f"view, Open on eBay, {url}"
    if image:
        headers["Attach"] = image
    requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                  headers=headers, timeout=20).raise_for_status()
