import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import uvicorn

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- НАСТРОЙКА GROQ ---
# Твой ключ уже вставлен
client = Groq(api_key="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")

class ProductRequest(BaseModel):
    name: str
    features: str
    marketplace: str

@app.post("/generate-description")
async def generate(data: ProductRequest):
    try:
        prompt = f"""
        Ты эксперт по маркетплейсам {data.marketplace}.
        Напиши продающее SEO-описание для товара.
        Название: {data.name}
        Характеристики: {data.features}
        Пиши на русском языке, структурировано, используй списки.
        """

        # ОБНОВЛЕННАЯ МОДЕЛЬ: llama-3.3-70b-versatile
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты эксперт-копирайтер для маркетплейсов."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024,
        )

        result = completion.choices[0].message.content

        if result:
            return {"description": result}
        else:
            return {"description": "Ошибка: ИИ не вернул ответ."}

    except Exception as e:
        print(f"!!! ОШИБКА GROQ: {e}")
        return {"description": f"Ошибка системы: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)