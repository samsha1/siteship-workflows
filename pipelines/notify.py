def notify_telegram(message: str, bot_token: str, chat_id: str) -> None:
    """
    Sends a notification message to a Telegram chat.
    """
    print(f"Sending Telegram message: {message}")
    # Placeholder logic
    # import requests
    # url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # data = {"chat_id": chat_id, "text": message}
    # requests.post(url, data=data)
    # TODO: Implement actual notification logic
    return "telegram notified"


def update_supabase_status(file_id: str, status: str, supabase_url: str, supabase_key: str) -> None:
    """
    Updates the status of a file in Supabase (e.g., after processing).
    """
    print(f"Updating Supabase status for {file_id} to {status}")
    # Placeholder logic
    # TODO: Implement actual Supabase update logic 
    return "supabase updated"