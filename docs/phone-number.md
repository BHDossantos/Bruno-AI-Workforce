# Changing the business phone number

The app uses **one** Twilio number for everything: texts, the caller-ID on calls,
the caller-ID on transfers that ring your cell, and the number printed on emails.
It lives in one setting, `business_phone` (`backend/app/phone_numbers.py`).

## Swap the number (no code change, no redeploy)

1. In Twilio, make sure the new number is active for **Voice and SMS**, and point
   its webhooks at this app (same URLs as the old number).
2. In the app: **Setup → Business phone number**, type the new number, **Save**.
   Saving also clears the older per-channel numbers (texting, insurance texting,
   caller-ID, transfer caller-ID, number on emails), so none of them can keep
   using the old number.
3. Check the list under that field: every line should show the new number.
   If a yellow warning lists env vars, delete those in **Render → bruno-backend →
   Environment**; env vars override the Setup page.
4. Release the old number in Twilio only after a test call and text work.

## Change the default in code (optional)

Edit one line in `backend/app/config.py`:

```python
business_phone: str = "+1XXXXXXXXXX"
```

A value saved in Setup, or a `BUSINESS_PHONE` env var, still wins over this default.

## Why the old number used to keep ringing

The number had been copied into five places: two code defaults, three Setup
fields saved in the database, plus the email signature default. Setup values
win over code, and a blank Setup field can't be saved, so an old saved value
could never be cleared from the page. Separately, deploys had been failing
since Nov 11, so code fixes never reached production.

Other carriers (SignalWire, Plivo, Vonage, self-hosted SIP) own their own
numbers on their own accounts, so they keep their own fields in Setup.
