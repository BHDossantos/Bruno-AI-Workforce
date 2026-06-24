"""Provider registry — the catalog of apps/accounts a user can connect.

Each provider declares how it authenticates, what fields it needs, what the
platform can do with it (capabilities), and which marketing-funnel stages it
serves. The funnel planner (app/funnel.py) reads these capabilities to build the
automated marketing & sales funnel for every connected account.

Compliance note: social networks (Instagram/Facebook/LinkedIn/TikTok/X) forbid
bot automation of DMs/follows. Where a capability is "assisted", the platform
PREPARES the content and queues it for one-click human action — it never
silently automates actions that violate a platform's Terms of Service. Posting
via official business APIs (Meta Graph, etc.) and ad management are fully
automatable and marked "auto".
"""
from __future__ import annotations

# Capability vocabulary (what the funnel engine can drive):
#   publish_auto    - publish posts/content via official API
#   publish_assist  - draft content, queue for one-click manual publish
#   dm_assist       - draft outreach DMs, queue for one-click manual send
#   email_auto      - send email automatically (own mailbox / ESP API)
#   sms_auto        - send SMS automatically (opt-in / warm only)
#   ads_auto        - create/pause campaigns & set budgets via API
#   crm_sync        - push/pull contacts & deals
#   commerce_sync   - read orders/customers, trigger post-purchase flows
#   analytics       - pull performance metrics
#   lead_capture    - ingest inbound leads/forms

# Funnel stages each provider can serve.
STAGES = ["attract", "capture", "nurture", "convert", "retain"]


def _field(key, label, secret=False, required=True, placeholder=""):
    return {"key": key, "label": label, "secret": secret, "required": required,
            "placeholder": placeholder}


PROVIDERS: list[dict] = [
    # ── Social (organic) ──────────────────────────────────────────────────────
    {
        "key": "instagram", "name": "Instagram", "category": "social", "icon": "📸",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Graph API access token", secret=True),
                   _field("ig_user_id", "Instagram business account ID", placeholder="1784xxxxxxxx")],
        "capabilities": ["publish_auto", "dm_assist", "analytics"],
        "stages": ["attract", "capture", "nurture"],
        "compliance": "Posts/Reels publish via the official Instagram Graph API (Business/Creator accounts). DMs are one-click assisted — never bot-sent.",
        "goals": ["followers", "leads", "sales"],
    },
    {
        "key": "facebook", "name": "Facebook Page", "category": "social", "icon": "👍",
        "auth_type": "api_key",
        "fields": [_field("page_access_token", "Page access token", secret=True),
                   _field("page_id", "Page ID")],
        "capabilities": ["publish_auto", "analytics", "lead_capture"],
        "stages": ["attract", "capture"],
        "compliance": "Publishes to your Page via the official Meta Graph API. Lead Ads forms ingest automatically.",
        "goals": ["followers", "leads", "sales"],
    },
    {
        "key": "linkedin", "name": "LinkedIn", "category": "social", "icon": "💼",
        "auth_type": "oauth",
        "fields": [_field("access_token", "OAuth access token (w_member_social)", secret=True),
                   _field("author_urn", "Author URN", placeholder="urn:li:person:xxxx or urn:li:organization:xxxx"),
                   _field("profile_url", "Your profile / company URL", secret=False, required=False)],
        "capabilities": ["publish_auto", "dm_assist", "analytics"],
        "stages": ["attract", "nurture", "convert"],
        "compliance": "Auto-publishes YOUR OWN posts via the official LinkedIn API "
                      "(w_member_social / w_organization_social). Automated connections "
                      "& DMs are forbidden by LinkedIn — those stay one-click assisted.",
        "goals": ["leads", "followers"],
    },
    {
        "key": "tiktok", "name": "TikTok", "category": "social", "icon": "🎵",
        "auth_type": "api_key",
        "fields": [_field("access_token", "TikTok API access token", secret=True),
                   _field("open_id", "Open ID", required=False)],
        "capabilities": ["publish_auto", "analytics"],
        "stages": ["attract"],
        "compliance": "Publishes via the official TikTok Content Posting API.",
        "goals": ["followers", "sales"],
    },
    {
        "key": "x_twitter", "name": "X (Twitter)", "category": "social", "icon": "🐦",
        "auth_type": "api_key",
        "fields": [_field("api_key", "API key", secret=True),
                   _field("api_secret", "API secret", secret=True),
                   _field("access_token", "Access token", secret=True),
                   _field("access_secret", "Access token secret", secret=True)],
        "capabilities": ["publish_auto", "analytics"],
        "stages": ["attract", "nurture"],
        "compliance": "Posts via the official X API v2.",
        "goals": ["followers", "leads"],
    },
    {
        "key": "youtube", "name": "YouTube", "category": "social", "icon": "▶️",
        "auth_type": "api_key",
        "fields": [_field("access_token", "YouTube Data API token", secret=True),
                   _field("channel_id", "Channel ID", required=False)],
        "capabilities": ["publish_assist", "analytics"],
        "stages": ["attract"],
        "compliance": "Video uploads are assisted; analytics pull via the YouTube Data API.",
        "goals": ["followers"],
    },
    {
        "key": "google_business", "name": "Google Business Profile", "category": "social", "icon": "📍",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Business Profile API token", secret=True),
                   _field("location_id", "Location ID")],
        "capabilities": ["publish_auto", "analytics", "lead_capture"],
        "stages": ["attract", "capture"],
        "compliance": "Posts updates & reads reviews via the Google Business Profile API.",
        "goals": ["leads", "sales"],
    },

    # ── Email / ESP ───────────────────────────────────────────────────────────
    {
        "key": "gmail", "name": "Gmail", "category": "email", "icon": "✉️",
        "auth_type": "oauth",
        "fields": [_field("email_address", "Email address", secret=False),
                   _field("refresh_token", "OAuth refresh token", secret=True),
                   _field("client_id", "OAuth client ID", secret=True, required=False),
                   _field("client_secret", "OAuth client secret", secret=True, required=False)],
        "capabilities": ["email_auto", "lead_capture"],
        "stages": ["capture", "nurture", "convert"],
        "compliance": "Sends & reads via the Gmail API on your own mailbox. CAN-SPAM footer + caps applied automatically.",
        "goals": ["leads", "sales", "bookings"],
    },
    {
        "key": "outlook", "name": "Outlook / Microsoft 365", "category": "email", "icon": "📨",
        "auth_type": "oauth",
        "fields": [_field("email_address", "Email address", secret=False),
                   _field("refresh_token", "OAuth refresh token", secret=True)],
        "capabilities": ["email_auto", "lead_capture"],
        "stages": ["capture", "nurture", "convert"],
        "compliance": "Sends & reads via the Microsoft Graph API on your own mailbox.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "mailchimp", "name": "Mailchimp", "category": "email", "icon": "🐵",
        "auth_type": "api_key",
        "fields": [_field("api_key", "API key", secret=True),
                   _field("audience_id", "Audience/List ID")],
        "capabilities": ["email_auto", "crm_sync", "analytics"],
        "stages": ["nurture", "convert"],
        "compliance": "Drives broadcast & automation campaigns via the Mailchimp Marketing API.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "klaviyo", "name": "Klaviyo", "category": "email", "icon": "💌",
        "auth_type": "api_key",
        "fields": [_field("api_key", "Private API key", secret=True)],
        "capabilities": ["email_auto", "sms_auto", "crm_sync", "analytics"],
        "stages": ["nurture", "convert", "retain"],
        "compliance": "Triggers email/SMS flows via the Klaviyo API (e-commerce focused).",
        "goals": ["sales", "leads"],
    },

    # ── CRM ───────────────────────────────────────────────────────────────────
    {
        "key": "hubspot", "name": "HubSpot", "category": "crm", "icon": "🟠",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Private app access token", secret=True)],
        "capabilities": ["crm_sync", "email_auto", "analytics", "lead_capture"],
        "stages": ["capture", "nurture", "convert", "retain"],
        "compliance": "Two-way sync of contacts & deals; can enroll in sequences via the HubSpot API.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "salesforce", "name": "Salesforce", "category": "crm", "icon": "☁️",
        "auth_type": "oauth",
        "fields": [_field("instance_url", "Instance URL", secret=False),
                   _field("access_token", "Access token", secret=True)],
        "capabilities": ["crm_sync", "analytics", "lead_capture"],
        "stages": ["capture", "convert", "retain"],
        "compliance": "Syncs leads/opportunities via the Salesforce REST API.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "pipedrive", "name": "Pipedrive", "category": "crm", "icon": "🟢",
        "auth_type": "api_key",
        "fields": [_field("api_token", "API token", secret=True),
                   _field("company_domain", "Company domain", required=False)],
        "capabilities": ["crm_sync", "analytics"],
        "stages": ["capture", "convert"],
        "compliance": "Syncs deals & contacts via the Pipedrive API.",
        "goals": ["leads", "sales"],
    },

    # ── Ads ───────────────────────────────────────────────────────────────────
    {
        "key": "meta_ads", "name": "Meta Ads (FB/IG)", "category": "ads", "icon": "📣",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Marketing API token", secret=True),
                   _field("ad_account_id", "Ad account ID", placeholder="act_1234567890")],
        "capabilities": ["ads_auto", "analytics", "lead_capture"],
        "stages": ["attract", "capture"],
        "compliance": "Creates/pauses campaigns & sets budgets via the Meta Marketing API.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "google_ads", "name": "Google Ads", "category": "ads", "icon": "🔍",
        "auth_type": "oauth",
        "fields": [_field("customer_id", "Customer ID", placeholder="123-456-7890"),
                   _field("developer_token", "Developer token", secret=True),
                   _field("refresh_token", "OAuth refresh token", secret=True)],
        "capabilities": ["ads_auto", "analytics"],
        "stages": ["attract"],
        "compliance": "Manages Search/PMax campaigns & budgets via the Google Ads API.",
        "goals": ["leads", "sales"],
    },
    {
        "key": "tiktok_ads", "name": "TikTok Ads", "category": "ads", "icon": "🎯",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Marketing API token", secret=True),
                   _field("advertiser_id", "Advertiser ID")],
        "capabilities": ["ads_auto", "analytics"],
        "stages": ["attract"],
        "compliance": "Manages campaigns via the TikTok Marketing API.",
        "goals": ["sales", "leads"],
    },

    # ── Commerce & payments ───────────────────────────────────────────────────
    {
        "key": "shopify", "name": "Shopify", "category": "commerce", "icon": "🛍️",
        "auth_type": "api_key",
        "fields": [_field("shop_domain", "myshop.myshopify.com", secret=False),
                   _field("admin_api_token", "Admin API access token", secret=True)],
        "capabilities": ["commerce_sync", "email_auto", "analytics", "lead_capture"],
        "stages": ["convert", "retain"],
        "compliance": "Reads orders/customers & triggers post-purchase + abandoned-cart flows via the Shopify Admin API.",
        "goals": ["sales"],
    },
    {
        "key": "woocommerce", "name": "WooCommerce", "category": "commerce", "icon": "🟣",
        "auth_type": "api_key",
        "fields": [_field("store_url", "Store URL", secret=False),
                   _field("consumer_key", "Consumer key", secret=True),
                   _field("consumer_secret", "Consumer secret", secret=True)],
        "capabilities": ["commerce_sync", "analytics"],
        "stages": ["convert", "retain"],
        "compliance": "Reads orders/customers via the WooCommerce REST API.",
        "goals": ["sales"],
    },
    {
        "key": "stripe", "name": "Stripe", "category": "commerce", "icon": "💳",
        "auth_type": "api_key",
        "fields": [_field("secret_key", "Secret key (sk_live_…)", secret=True)],
        "capabilities": ["commerce_sync", "analytics"],
        "stages": ["convert", "retain"],
        "compliance": "Reads payments/customers to trigger receipts, upsells & win-back flows via the Stripe API.",
        "goals": ["sales"],
    },

    # ── Messaging ─────────────────────────────────────────────────────────────
    {
        "key": "twilio_sms", "name": "Twilio SMS", "category": "messaging", "icon": "💬",
        "auth_type": "api_key",
        "fields": [_field("account_sid", "Account SID", secret=True),
                   _field("auth_token", "Auth token", secret=True),
                   _field("from_number", "From number (+1…)", secret=False)],
        "capabilities": ["sms_auto", "lead_capture"],
        "stages": ["nurture", "convert"],
        "compliance": "Two-way SMS to opted-in / warm contacts only (TCPA). Auto-texts after a lead replies.",
        "goals": ["leads", "sales", "bookings"],
    },
    {
        "key": "whatsapp", "name": "WhatsApp Business", "category": "messaging", "icon": "🟩",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Cloud API token", secret=True),
                   _field("phone_number_id", "Phone number ID")],
        "capabilities": ["sms_auto", "lead_capture"],
        "stages": ["nurture", "convert"],
        "compliance": "Sends template/session messages via the official WhatsApp Cloud API (opt-in required).",
        "goals": ["leads", "sales", "bookings"],
    },
    {
        "key": "calendly", "name": "Calendly", "category": "scheduling", "icon": "📅",
        "auth_type": "api_key",
        "fields": [_field("access_token", "Personal access token", secret=True),
                   _field("scheduling_url", "Booking link", secret=False)],
        "capabilities": ["lead_capture", "analytics"],
        "stages": ["convert"],
        "compliance": "Adds your booking link to outreach and ingests booked meetings via the Calendly API.",
        "goals": ["bookings", "sales"],
    },
]

_BY_KEY = {p["key"]: p for p in PROVIDERS}


def list_providers() -> list[dict]:
    """Public catalog (no secret values)."""
    return PROVIDERS


def get_provider(key: str) -> dict | None:
    return _BY_KEY.get(key)


def required_fields(key: str) -> list[str]:
    p = _BY_KEY.get(key) or {}
    return [f["key"] for f in p.get("fields", []) if f.get("required")]


def secret_field_keys(key: str) -> set[str]:
    p = _BY_KEY.get(key) or {}
    return {f["key"] for f in p.get("fields", []) if f.get("secret")}


def capabilities(key: str) -> list[str]:
    p = _BY_KEY.get(key) or {}
    return list(p.get("capabilities", []))
