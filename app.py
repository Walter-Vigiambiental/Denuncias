import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import smtplib
from email.message import EmailMessage
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# -------------------------
# Config
# -------------------------
HISTORICO_PATH = os.environ.get("HISTORICO_PATH", "historico.json")  # default historico.json (or set env var to /tmp/historico.json)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))  # 465 (SSL) or 587 (STARTTLS)
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
SENHA_EXCLUSAO = os.environ.get("SENHA_EXCLUSAO", "minhasenha123")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "troque_esta_chave")

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
# Helper: enviar email (threaded)
# -------------------------
def _envia_email_sync(destino, assunto, corpo, anexos_paths=None):
    if not EMAIL_USER or not EMAIL_PASS:
        print("Variáveis de e-mail não configuradas; não será enviado.")
        return False

    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_USER
        msg["To"] = destino
        msg["Subject"] = assunto
        msg.set_content(corpo)

        # anexos (opcionais)
        if anexos_paths:
            for p in anexos_paths:
                try:
                    with open(p, "rb") as af:
                        data = af.read()
                        filename = os.path.basename(p)
                        msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=filename)
                except Exception as e:
                    print("Falha ao anexar", p, e)

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20) as smtp:
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(EMAIL_USER, EMAIL_PASS)
                smtp.send_message(msg)

        print("E-mail enviado para", destino)
        return True
    except Exception as e:
        print("Erro envio e-mail:", e)
        return False

def envia_email_background(destino, assunto, corpo, anexos_paths=None):
    thread = threading.Thread(target=_envia_email_sync, args=(destino, assunto, corpo, anexos_paths), daemon=True)
    thread.start()

# -------------------------
# Rotas
# -------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    """
    Página principal com abas:
     - aba=denuncias (form)
     - aba=historico  (lista)
    """
    aba = request.args.get("aba", "denuncias")
    historico = _carregar_historico()

    if request.method == "POST":
        # campos do formulário
        denunciante = request.form.get("denunciante", "").strip()
        email_usuario = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        tipo = request.form.get("tipo", "").strip()  # ex: "Qualidade da Água"
        tipo_problema = request.form.get("tipo_problema", "").strip()  # se aplicável
        outro_problema = request.form.get("outro_problema", "").strip()
        local = request.form.get("local", "").strip()
        endereco = request.form.get("endereco", "").strip()
        descricao = request.form.get("descricao", "").strip()

        # construir descrição do problema final
        problema_final = ""
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

        # salvar no histórico
        hist = _carregar_historico()
        hist.append(registro)
        saved = _salvar_historico(hist)
        if not saved:
            flash("Erro ao salvar o registro. Verifique permissões de disco.", "erro")
            return redirect(url_for("index", aba="denuncias"))

        # gerar relatório simples (txt) temporário (opcional / para anexar)
        rel_path = None
        try:
            rel_path = f"/tmp/relatorio_{registro['Nº Protocolo']}.txt"
            with open(rel_path, "w", encoding="utf-8") as rf:
                for k, v in registro.items():
                    rf.write(f"{k}: {v}\n")
        except Exception as e:
            print("Não foi possível criar relatorio:", e)
            rel_path = None

        # enviar e-mail em background (se e-mail do denunciante informado, envia pra ele e bcc pro laboratório)
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

        # destinatários: se houver email do usuário, envia para ele; sempre enviar para o próprio EMAIL_USER em cópia (adapte se quiser)
        destinatario = email_usuario if email_usuario else (EMAIL_USER or "")
        if destinatario:
            envia_email_background(destinatario, assunto, corpo, anexos_paths=[rel_path] if rel_path else None)
        else:
            # como fallback, envie para o EMAIL_USER (se configurado)
            if EMAIL_USER:
                envia_email_background(EMAIL_USER, assunto, corpo, anexos_paths=[rel_path] if rel_path else None)

        flash("Denúncia registrada com sucesso.", "sucesso")
        return redirect(url_for("index", aba="historico"))

    # GET: renderiza
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

    ok = _salvar_historico(novo)
    if ok:
        flash(f"Registro {protocolo} excluído com sucesso.", "sucesso")
    else:
        flash("Erro ao excluir o registro (salvar falhou).", "erro")

    return redirect(url_for("index", aba="historico"))

# Exporte PDF do histórico (opcional)
@app.route("/exportar_pdf")
def exportar_pdf():
    historico = _carregar_historico()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 80

    # cabeçalho
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
# Run (use PORT env var when deployed)
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
