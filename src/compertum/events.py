"""Replay only safe durable M0 internal events."""
from .domain import ContractError

def replay_safe_messages(store,messages):
    receipts=[];withheld=[]
    for message in messages:
        if message['kind']=='BROKER_SIDE_EFFECT':withheld.append(message['event_id']);continue
        receipts.append(store.accept_message(message))
    return {'receipts':receipts,'withheld_side_effects':withheld}
