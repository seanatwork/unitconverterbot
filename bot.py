import os
import re
import logging
from datetime import datetime
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, InlineQueryHandler, filters, ContextTypes
from pint import UnitRegistry, UndefinedUnitError, DimensionalityError
import pytz

logging.basicConfig(level=logging.INFO)
ureg = UnitRegistry()

HELP_TEXT = """
*Unit Converter Bot*

Send a message like:
• `100 kg to lbs`
• `32 fahrenheit to celsius`
• `60 mph to kph`
• `5 feet to meters`
• `1 mile to km`
• `500 ml to cups`
• `3pm EST to PST`
• `15:30 GMT to JST`
• `now UTC to America/New_York`

You can also use me inline in any chat:
`@your_bot_name 100 kg to lbs`

/help — show this message
"""

UNIT_ALIASES = {
    "kph": "km/h",
    "mph": "mi/h",
    "celsius": "degC",
    "fahrenheit": "degF",
    "kelvin": "kelvin",
    "c": "degC",
    "f": "degF",
    "k": "kelvin",
    "lbs": "lb",
    "pounds": "lb",
    "pound": "lb",
    "kilograms": "kg",
    "kilogram": "kg",
    "grams": "g",
    "gram": "g",
    "ounces": "oz",
    "ounce": "oz",
    "meters": "m",
    "meter": "m",
    "feet": "ft",
    "foot": "ft",
    "inches": "inch",
    "miles": "mi",
    "mile": "mi",
    "kilometers": "km",
    "kilometer": "km",
    "liters": "L",
    "liter": "L",
    "litres": "L",
    "litre": "L",
    "milliliters": "mL",
    "milliliter": "mL",
    "gallons": "gallon",
    "pints": "pint",
    "cups": "cup",
}

TIMEZONE_ALIASES = {
    "est": "US/Eastern",
    "edt": "US/Eastern",
    "pst": "US/Pacific",
    "pdt": "US/Pacific",
    "cst": "US/Central",
    "cdt": "US/Central",
    "mst": "US/Mountain",
    "mdt": "US/Mountain",
    "gmt": "GMT",
    "utc": "UTC",
    "bst": "Europe/London",
    "cet": "Europe/Paris",
    "jst": "Asia/Tokyo",
    "ist": "Asia/Kolkata",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
}

def normalize(unit: str) -> str:
    return UNIT_ALIASES.get(unit.lower(), unit)

def normalize_timezone(tz: str) -> str:
    return TIMEZONE_ALIASES.get(tz.lower(), tz)

def convert_timezone(text: str) -> str:
    # Pattern for time conversion: "3pm EST to PST", "15:30 GMT to JST", "now UTC to America/New_York"
    # Requires either "now" or a proper time format (HH:MM or H{am/pm}) followed by timezone names
    time_pattern = r"^(now|\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\s+(.+?)\s+(?:to|in|->|→)\s+(.+)$"
    match = re.match(time_pattern, text.strip(), re.IGNORECASE)
    if not match:
        return None

    time_str, from_tz, to_tz = match.groups()
    from_tz = normalize_timezone(from_tz.strip())
    to_tz = normalize_timezone(to_tz.strip())
    
    try:
        # Validate timezones
        if from_tz not in pytz.all_timezones:
            return f"Unknown timezone: {from_tz}"
        if to_tz not in pytz.all_timezones:
            return f"Unknown timezone: {to_tz}"
        
        from_tz_obj = pytz.timezone(from_tz)
        to_tz_obj = pytz.timezone(to_tz)
        
        # Parse time
        if time_str.lower() == "now":
            now = datetime.now(from_tz_obj)
        else:
            # Determine if AM/PM is present
            has_ampm = bool(re.search(r'(am|pm)', time_str, re.IGNORECASE))
            if has_ampm:
                # Format like "3pm" or "3:30pm"
                if ":" in time_str:
                    time_format = "%I:%M%p"
                else:
                    time_format = "%I%p"
                time_obj = datetime.strptime(time_str.lower(), time_format).time()
                now = datetime.now(from_tz_obj).replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
            else:
                # Format like "15:30" or "15"
                if ":" in time_str:
                    time_format = "%H:%M"
                else:
                    time_format = "%H"
                time_obj = datetime.strptime(time_str, time_format).time()
                now = datetime.now(from_tz_obj).replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
        
        # Convert timezone
        converted_time = now.astimezone(to_tz_obj)
        
        # Format result
        from_time_str = now.strftime("%I:%M %p").lstrip("0")
        to_time_str = converted_time.strftime("%I:%M %p").lstrip("0")
        from_date = now.strftime("%Y-%m-%d")
        to_date = converted_time.strftime("%Y-%m-%d")
        
        if from_date == to_date:
            return f"{from_time_str} {from_tz} = *{to_time_str} {to_tz}*"
        else:
            return f"{from_time_str} {from_tz} ({from_date}) = *{to_time_str} {to_tz} ({to_date})*"
            
    except Exception as e:
        return f"Time conversion error: {e}"

def parse_and_convert(text: str) -> str:
    # Try timezone conversion first
    timezone_result = convert_timezone(text)
    if timezone_result:
        return timezone_result
    
    # Fall back to unit conversion
    pattern = r"^([\d.,]+)\s+(.+?)\s+(?:to|in|->|→)\s+(.+)$"
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    if not match:
        return None

    value_str, from_unit, to_unit = match.groups()
    value = float(value_str.replace(",", ""))
    from_unit = normalize(from_unit.strip())
    to_unit = normalize(to_unit.strip())

    try:
        qty = ureg.Quantity(value, from_unit)
        result = qty.to(to_unit)
        result_val = result.magnitude
        if abs(result_val) >= 1000 or (abs(result_val) < 0.01 and result_val != 0):
            formatted = f"{result_val:,.4g}"
        else:
            formatted = f"{result_val:,.4f}".rstrip("0").rstrip(".")
        return f"{value:g} {from_unit} = *{formatted} {to_unit}*"
    except DimensionalityError:
        return f"Cannot convert {from_unit} to {to_unit} — incompatible units."
    except UndefinedUnitError as e:
        return f"Unknown unit: {e}"
    except Exception as e:
        return f"Error: {e}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return

    result = parse_and_convert(query)
    if result is None:
        results = [
            InlineQueryResultArticle(
                id="help",
                title="Format: 100 kg to lbs",
                description="Type a conversion like: 60 mph to kph",
                input_message_content=InputTextMessageContent("Format: `100 kg to lbs`", parse_mode="Markdown"),
            )
        ]
    else:
        plain = result.replace("*", "")
        results = [
            InlineQueryResultArticle(
                id="result",
                title=plain,
                description=query,
                input_message_content=InputTextMessageContent(result, parse_mode="Markdown"),
            )
        ]

    await update.inline_query.answer(results, cache_time=30)

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    result = parse_and_convert(text)
    if result is None:
        await update.message.reply_text(
            "Format: `100 kg to lbs`\nSend /help for examples.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(result, parse_mode="Markdown")

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, convert))
    app.run_polling()

if __name__ == "__main__":
    main()
