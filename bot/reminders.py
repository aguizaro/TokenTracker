from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def schedule_reminder(user_id, message, delay_seconds):
    scheduler.add_job(
        func=send_reminder,
        trigger='date',
        run_date=datetime.now() + timedelta(seconds=delay_seconds),
        args=[user_id, message]
    )

async def send_reminder(user_id, message):
    # Logic to send a DM using the bot
