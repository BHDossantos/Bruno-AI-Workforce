"""Last-mile suppression check, serialized with ORM suppression inserts on Postgres."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from sqlalchemy import event, select, text, func
from .models import DoNotContact, Message, Lead, Restaurant, Contact
import re

_active = ContextVar('suppression_boundary', default=None)


def identity(channel, recipient):
    from .compliance import _email_key, _phone_key
    kind = 'email' if channel in ('email', 'campaign') or '@' in (recipient or '') else 'phone'
    value = _email_key(recipient) if kind == 'email' else _phone_key((recipient or '').removeprefix('whatsapp:'))
    if not value:
        raise ValueError('Missing suppression identity')
    return kind, value


def lock_key(kind, value):
    return int.from_bytes(sha256(f'suppression:{kind}:{value}'.encode()).digest()[:8], 'big', signed=True)


def blocked(connection, kind, value):
    if connection.execute(select(DoNotContact.id).where(DoNotContact.kind == kind,
                         DoNotContact.value == value).limit(1)).first():
        return 'do_not_contact'
    if kind == 'email' and connection.execute(select(Message.id).where(
        func.lower(func.trim(Message.to_email)) == value, Message.direction == 'outbound',
        Message.channel == 'email',
        (func.lower(Message.delivery_status).in_(['bounced', 'complained']) |
         func.lower(Message.status).in_(['bounced', 'suppressed']))).limit(1)).first():
        return 'bounce_or_suppression'
    terminal = ('do_not_contact', 'do not contact', 'unsubscribed', 'suppressed', 'bounced')
    for model in (Lead, Restaurant, Contact):
        if kind == 'email':
            if connection.execute(select(model.id).where(func.lower(func.trim(model.email)) == value,
                    func.lower(model.status).in_(terminal)).limit(1)).first():
                return 'contact_suppressed'
        else:
            for phone, in connection.execute(select(model.phone).where(func.lower(model.status).in_(terminal))):
                if phone and re.sub(r'\D', '', phone)[-10:] == value:
                    return 'contact_suppressed'
    if kind == 'phone':
        from .sms_engine import _STOP_WORDS
        for recipient, body in connection.execute(select(Message.to_email, Message.body).where(
                Message.direction == 'inbound', Message.channel.in_(['sms', 'whatsapp']))):
            words = re.findall(r'[a-z]+', (body or '').lower())
            if recipient and re.sub(r'\D', '', recipient)[-10:] == value and words and words[0] in _STOP_WORDS:
                return 'inbound_opt_out'
    return None


@event.listens_for(Message, 'before_insert')
@event.listens_for(Message, 'before_update')
def serialize_text_optout(mapper, connection, target):
    if target.direction == 'inbound' and target.channel in ('sms', 'whatsapp'):
        from .sms_engine import _STOP_WORDS
        words = re.findall(r'[a-z]+', (target.body or '').lower())
        if words and words[0] in _STOP_WORDS and target.to_email:
            kind, value = identity('sms', target.to_email)
            if connection.dialect.name == 'postgresql':
                connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key(kind, value)})



@contextmanager
def boundary(engine, channel, recipient):
    key = identity(channel, recipient)
    if _active.get() == key:
        yield None
        return
    with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key(*key)})
        reason = blocked(connection, *key)
        token = _active.set(key)
        try:
            yield reason
        finally:
            _active.reset(token)


@event.listens_for(DoNotContact, 'before_insert')
def serialize_suppression(mapper, connection, target):
    # Covers all existing ORM insert paths, including opt-outs after draft creation.
    kind, value = identity('email' if target.kind == 'email' else 'sms', target.value)
    target.value = value
    if connection.dialect.name == 'postgresql':
        connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key(kind, value)})


@event.listens_for(Message, 'before_update')
def serialize_bounce(mapper, connection, target):
    if target.channel == 'email' and target.direction == 'outbound' and (
        (target.delivery_status or '').lower() in ('bounced', 'complained') or
        (target.status or '').lower() in ('bounced', 'suppressed')):
        kind, value = identity('email', target.to_email)
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key(kind, value)})



def serialize_contact_suppression(mapper, connection, target):
    if (target.status or '').lower() not in ('do_not_contact', 'do not contact', 'unsubscribed', 'suppressed', 'bounced'):
        return
    keys = []
    if target.email:
        keys.append(identity('email', target.email))
    if target.phone:
        keys.append(identity('sms', target.phone))
    if connection.dialect.name == 'postgresql':
        for kind, value in sorted(keys):
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key(kind, value)})


for model in (Lead, Restaurant, Contact):
    event.listen(model, 'before_insert', serialize_contact_suppression)
    event.listen(model, 'before_update', serialize_contact_suppression)
