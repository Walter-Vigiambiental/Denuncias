import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import requests  # usado para enviar e-mail via Resend API

# -------------------------
# Configurações
# -------------------------
HISTORICO_PATH = os.environ.get("HISTORICO_PATH", "historico.json")
SENHA_EXCLUSAO = os.environ.get("SENHA_EXCLUSAO", "minhasenha123")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "re_j8zp6WGE_6ErTGGiEZ7D8RnKm5UF53euf")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")  # chave do resend

# -------------------------
# App init
# -------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = FLASK_SECRET_KEY


# -------------------------
# Helpers: JSON I/O
# -------------------------
def _carregar_historico():
    try:
        if not os.path.exists(HISTORICO_PATH):
            return []
        with open(HISTORICO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []
    except Exception as e:
        print("Erro ao carregar histórico:", e)
        return []


def _salvar_historico(lista):
    try:
        with open(HISTORICO_PATH, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print("Erro ao salvar histórico:", e)
        return False


def gerar_protocolo():
    return f"PROTO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


# -------------------------
# Envio de e-mail via Resend API
# -------------------------
def _envia_email_sync(destino, assunto, corpo):
    if not RESEND_API_KEY:
        print("❌ RESEND_API_KEY não configurada.")
        return False

    try:
        payload = {
            "from": "Denúncias Vigiagua <denuncias@resend.dev>",
            "to": [destino],
            "subject": assunto,
            "text": corpo
        }

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )

        if response.status_code == 200:
            print(f"✅ E-mail enviado com sucesso via Resend para {destino}")
            return True
        else:
            print(f"❌ Erro Resend: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print("❌ Falha ao enviar e-mail via Resend:", e)
        return False


def envia_email_background(destino, assunto, corpo):
    thread = threading.Thread(target=_envia_email_sync, args=(destino, assunto, corpo), daemon=True)
    thread.start()


# -------------------------
# Rotas principais
# -------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    aba = request.args.get("aba", "denuncias")
    historico = _carregar_historico()

    if request.method == "POST":
        # campos do formulário
        denunciante = request.form.get("denunciante", "").strip()
        email_usuario = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        tipo = request.form.get("tipo", "").strip()
        tipo_problema = request.form.get("tipo_problema", "").strip()
        outro_problema = request.form.get("outro_problema", "").strip()
        local = request.form.get("local", "").strip()
        endereco = request.form.get("endereco", "").strip()
        descricao = request.form.get("descricao", "").strip()

        # tipo de problema final
        if tipo == "Qualidade da Água":
            if tipo_problema == "Outros":
                problema_final = outro_problema or "Outros (não especificado)"
            else:
                problema_final = tipo_problema
        else:
            problema_final = ""

        # validação mínima
        if not denunciante or not tipo or not local or not endereco:
            flash("Preencha os campos obrigatórios (Denunciante, Tipo, Local e Endereço).", "erro")
            return redirect(url_for("index", aba="denuncias"))

        registro = {
            "Nº Protocolo": gerar_protocolo(),
            "Data Denúncia": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Denunciante": denunciante,
            "Tipo Denúncia": tipo,
            "Tipo Problema": problema_final,
            "Local": local,
            "Endereço": endereco,
            "Descrição": descricao,
            "E-mail": email_usuario,
            "Telefone Contato": telefone
        }

        # salva no histórico
        hist = _carregar_historico()
        hist.append(registro)
        if not _salvar_historico(hist):
            flash("Erro ao salvar o registro. Verifique permissões de disco.", "erro")
            return redirect(url_for("index", aba="denuncias"))

        # enviar e-mail (assíncrono)
        assunto = f"Denúncia registrada: {registro['Nº Protocolo']}"
        corpo = (
            f"Protocolo: {registro['Nº Protocolo']}\n"
            f"Data: {registro['Data Denúncia']}\n"
            f"Denunciante: {registro['Denunciante']}\n"
            f"Tipo: {registro['Tipo Denúncia']}\n"
            f"Tipo Problema: {registro['Tipo Problema']}\n"
            f"Local: {registro['Local']}\n"
            f"Endereço: {registro['Endereço']}\n"
            f"Descrição: {registro['Descrição']}\n"
            f"Telefone: {registro['Telefone Contato']}\n"
        )

        destinatario = email_usuario if email_usuario else "denuncias@resend.dev"
        envia_email_background(destinatario, assunto, corpo)

        flash("Denúncia registrada com sucesso.", "sucesso")
        return redirect(url_for("index", aba="historico"))

    return render_template("formulario.html", historico=historico, aba=aba)


@app.route("/excluir", methods=["POST"])
def excluir():
    protocolo = request.form.get("protocolo")
    senha = request.form.get("senha", "")

    if senha != SENHA_EXCLUSAO:
        flash("Senha incorreta. Exclusão não autorizada.", "erro")
        return redirect(url_for("index", aba="historico"))

    historico = _carregar_historico()
    novo = [r for r in historico if r.get("Nº Protocolo") != protocolo]

    if len(novo) == len(historico):
        flash("Protocolo não encontrado. Nada foi excluído.", "alerta")
        return redirect(url_for("index", aba="historico"))

    if _salvar_historico(novo):
        flash(f"Registro {protocolo} excluído com sucesso.", "sucesso")
    else:
        flash("Erro ao excluir o registro.", "erro")

    return redirect(url_for("index", aba="historico"))


@app.route("/exportar_pdf")
def exportar_pdf():
    historico = _carregar_historico()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 80

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Histórico de Denúncias")
    y -= 30
    pdf.setFont("Helvetica", 10)

    for item in historico:
        linhas = [
            f"Protocolo: {item.get('Nº Protocolo','')}",
            f"Data: {item.get('Data Denúncia','')}",
            f"Denunciante: {item.get('Denunciante','')}",
            f"Tipo: {item.get('Tipo Denúncia','')}",
            f"Tipo Problema: {item.get('Tipo Problema','')}",
            f"Local: {item.get('Local','')}",
            f"Endereço: {item.get('Endereço','')}",
            f"Descrição: {item.get('Descrição','')}",
            "-" * 80
        ]
        for l in linhas:
            pdf.drawString(40, y, l)
            y -= 14
            if y < 60:
                pdf.showPage()
                y = height - 80
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="historico_denuncias.pdf", mimetype="application/pdf")


# -------------------------
# Execução
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))




