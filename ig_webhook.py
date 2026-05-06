from flask import Flask, request
from openai import OpenAI
import requests
import os
import threading
import time

lock = threading.Lock()

app = Flask(__name__)

already_replied = set()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")

print("TOKEN IG DÉBUT :", IG_ACCESS_TOKEN[:10])
print("TOKEN IG FIN :", IG_ACCESS_TOKEN[-10:])
print("TOKEN IG LONGUEUR :", len(IG_ACCESS_TOKEN))

VERIFY_TOKEN = "mon_token_secret_123"

client = OpenAI(api_key=OPENAI_API_KEY)

PROMPT = """
Tu es l’assistante Instagram d’un créateur de contenu spécialisé dans le style élégant, esthétique et classique intemporel.

Ta mission est de répondre automatiquement aux commentaires sous ses posts.

RÈGLES STRICTES :

1. LANGUE (OBLIGATOIRE) :
- Si le commentaire est en anglais → réponds UNIQUEMENT en anglais
- Si le commentaire est en français → réponds UNIQUEMENT en français
- Si le commentaire est en italien → réponds UNIQUEMENT en italien
- Ne mélange JAMAIS les langues

2. TON :
- Élégant, naturel, chaleureux
- Jamais robotique
- Toujours positif
- Raffiné et authentique

3. LONGUEUR :
- Réponse très courte (1 phrase)

4. EMOJIS :
- Utilise uniquement 😍 et 🔥
- Maximum 2 emojis

5. VARIATION (TRÈS IMPORTANT) :
- Ne répète jamais exactement la même réponse
- Varie naturellement les formulations
- Alterne entre plusieurs façons de dire merci

6. PERSONNALISATION :
- Adapte légèrement la réponse au commentaire

7. CRITIQUES :
- Réponds avec élégance, jamais agressif

IMPORTANT :
- Ne traduis pas, réponds directement dans la langue détectée
- Ne donne aucune explication
- Retourne uniquement la réponse
- Réponse naturelle, comme un humain
"""

def get_comment_text(comment_id: str) -> str:
    url = f"https://graph.facebook.com/v25.0/{comment_id}"
    params = {
        "fields": "text,username",
        "access_token": IG_ACCESS_TOKEN
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("text", "")

def generate_reply(comment_text: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=PROMPT + "\nCommentaire : " + comment_text
    )
    return response.output_text.strip()

def publish_reply(comment_id: str, reply_text: str):
    url = f"https://graph.facebook.com/v25.0/{comment_id}/replies"
    data = {
        "message": reply_text,
        "access_token": IG_ACCESS_TOKEN
    }

    r = requests.post(url, data=data, timeout=20)

    print("STATUS PUBLICATION :", r.status_code)
    print("RÉPONSE META :", r.text)

    r.raise_for_status()
    return r.json()

@app.route("/webhook", methods=["GET"])
def verify():
    challenge = request.args.get("hub.challenge")
    return challenge or "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    print("BODY REÇU :", body)

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                print("CHANGE :", change)

                if change.get("field") != "comments":
                    print("Événement non-commentaire ignoré")
                    continue     

                value = change.get("value", {})
                comment_id = value.get("id")

                author_username = value.get("from", {}).get("username", "")

                if author_username == "iam___angeo":
                    print("Commentaire de moi-même ignoré")
                    continue

                if value.get("parent_id"):
                    print("Réponse à un commentaire ignorée")
                    continue

                if not comment_id:
                    continue

                with lock: 
                   if comment_id in already_replied:
                       print("Déjà répondu, on ignore")
                       continue
                   already_replied.add(comment_id)

                print("COMMENT ID :", comment_id)

                comment_text = value.get("text", "")
                print("COMMENT TEXT :", comment_text)

                if not comment_text.strip():
                    continue

                reply = generate_reply(comment_text)
                print("REPLY :", reply)

                def delayed_reply(comment_id, reply):
                    try:
                        print("Attente 5 secondes...")
                        time.sleep(5)
                        publish_reply(comment_id, reply)
                        print("Réponse envoyée")
                    except Exception as e:
                        print("Erreur pendant la réponse différée :", e)

                threading.Thread(target=delayed_reply, args=(comment_id, reply)).start()
                print("Réponse programmée")

        return "EVENT_RECEIVED", 200

    except Exception as e:
        print("Erreur webhook :", e)
        return "ERROR", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
