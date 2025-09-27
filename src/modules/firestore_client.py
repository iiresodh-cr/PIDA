# src/modules/firestore_client.py

import datetime
from google.cloud import firestore
from src.config import log

# Inicializa el cliente de Firestore.
# Se conectará automáticamente usando las credenciales del entorno de Cloud Run.
db = firestore.AsyncClient()

async def get_or_create_conversation(user_id: str, conversation_id: str | None = None) -> dict:
    """
    Obtiene una conversación por su ID o crea una nueva si no se proporciona un ID.
    También actualiza el título si es un "Nuevo Chat".
    """
    if conversation_id:
        log.info(f"Obteniendo conversación existente: {conversation_id}")
        convo_ref = db.collection('users').document(user_id).collection('conversations').document(conversation_id)
        convo = await convo_ref.get()
        if convo.exists:
            return {"id": convo.id, **convo.to_dict()}
    
    # Si no hay ID o no se encontró, crea una nueva
    log.info(f"Creando nueva conversación para el usuario: {user_id}")
    new_convo_ref = db.collection('users').document(user_id).collection('conversations').document()
    convo_data = {
        'title': 'Nuevo Chat',
        'created_at': firestore.SERVER_TIMESTAMP
    }
    await new_convo_ref.set(convo_data)
    return {"id": new_convo_ref.id, **convo_data}

async def add_message_to_conversation(user_id: str, conversation_id: str, role: str, content: str):
    """Añade un mensaje a la subcolección 'messages' de una conversación."""
    log.info(f"Añadiendo mensaje de '{role}' a la conversación {conversation_id}")
    message_ref = db.collection('users').document(user_id).collection('conversations').document(conversation_id).collection('messages').document()
    await message_ref.set({
        'role': role,
        'content': content,
        'timestamp': firestore.SERVER_TIMESTAMP
    })

async def get_conversation_history(user_id: str, conversation_id: str) -> list:
    """Obtiene el historial de mensajes de una conversación, ordenado por tiempo."""
    log.info(f"Obteniendo historial para la conversación: {conversation_id}")
    messages_ref = db.collection('users').document(user_id).collection('conversations').document(conversation_id).collection('messages').order_by('timestamp')
    messages = []
    async for doc in messages_ref.stream():
        messages.append(doc.to_dict())
    return messages

async def update_conversation_title(user_id: str, conversation_id: str, new_title: str):
    """Actualiza el título de una conversación."""
    log.info(f"Actualizando título de la conversación {conversation_id} a '{new_title}'")
    convo_ref = db.collection('users').document(user_id).collection('conversations').document(conversation_id)
    await convo_ref.update({'title': new_title})

async def get_user_conversations(user_id: str) -> list:
    """Obtiene la lista de todas las conversaciones de un usuario."""
    log.info(f"Obteniendo lista de conversaciones para el usuario: {user_id}")
    convos_ref = db.collection('users').document(user_id).collection('conversations').order_by('created_at', direction=firestore.Query.DESCENDING)
    conversations = []
    async for doc in convos_ref.stream():
        convo_data = doc.to_dict()
        conversations.append({
            "id": doc.id,
            "title": convo_data.get("title", "Conversación sin título")
        })
    return conversations
