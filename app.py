from flask import Flask, render_template, request, redirect, send_file
import json, os
from datetime import datetime
import smtplib
from email.message import EmailMessage
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

app = Flask(__name__)
HISTORICO_PATH = "historico.json"
SENHA_EXCLUSAO = "minhasenha123"
EMAIL_LABORATORIO = "laboraguamoc@yahoo.com"

def gerar_protocolo():
    return f"PROTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def carregar_historico():
    if os.path.exists(HISTORICO_PATH):
        with open(HISTORICO_PATH, "r") as f:
            return json.load(f)
    return []

def salvar_historico(dados):
    historico = carregar_historico()
    historico.append(dados)
    with open(HISTORICO_PATH, "w") as f:
        json.dump(historico, f, indent=4)

def gerar_relatorio(dados):
    nome_arquivo = f"relatorio_{dados['Nº Protocolo']}.txt"
    with open(nome_arquivo, "w") as f:
        for chave, valor in dados.items():
            f.write(f"{chave}: {valor}\n")
    return nome_arquivo

def enviar_email(dados, relatorio_path):
    config = {
        "email": os.environ.get("EMAIL_REMETENTE"),
        "senha": os.environ.get("EMAIL_SENHA")
    }

    msg = EmailMessage()
    msg["Subject"] = f"Denúncia {dados['Nº Protocolo']}"
    msg["From"] = config["email"]
    msg["To"] = dados["E-mail"]
    msg["Bcc"] = EMAIL_LABORATORIO
    msg.set_content("Segue o relatório da denúncia registrada.")

    with open(relatorio_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(relatorio_path)
        msg.add_attachment(file_data, maintype="application", subtype="octet-stream", filename=file_name)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config["email"], config["senha"])
        smtp.send_message(msg)

@app.route("/", methods=["GET", "POST"])
def formulario():
    historico = carregar_historico()

    if request.method == "POST":
        email_usuario = request.form.get("email", "").strip()
        tipo = request.form.get("tipo", "").strip()
        local = request.form.get("local", "").strip()
        endereco = request.form.get("endereco", "").strip()
        denunciante = request.form.get("denunciante", "").strip()
        telefone = request.form.get("telefone", "").strip()

        duplicada = any(
            d.get("Denunciante", "") == denunciante and
            d.get("Tipo Denúncia", "") == tipo and
            d.get("Local", "") == local and
            d.get("Endereço", "") == endereco and
            d.get("E-mail", "") == email_usuario and
            d.get("Telefone Contato", "") == telefone
            for d in historico
        )

        if not duplicada:
            dados = {
                "Nº Protocolo": gerar_protocolo(),
                "Data Denúncia": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "Denunciante": denunciante,
                "Tipo Denúncia": tipo,
                "Local": local,
                "Endereço": endereco,
                "E-mail": email_usuario,
                "Telefone Contato": telefone
            }

            salvar_historico(dados)
            relatorio = gerar_relatorio(dados)

            if email_usuario:
                enviar_email(dados, relatorio)

        return redirect("/")

    mes = request.args.get("mes")
    ano = request.args.get("ano")
    aba = request.args.get("aba", "formulario")

    historico_filtrado = []
    for item in historico:
        data = item.get("Data Denúncia", "")
        partes = data.split("/")
        if len(partes) < 3:
            continue
        item_mes = partes[1]
        item_ano = partes[2].split(" ")[0]

        if (not mes or item_mes == mes) and (not ano or item_ano == ano):
            historico_filtrado.append(item)

    return render_template("formulario.html", historico=historico_filtrado, historico_original=historico, request=request, aba=aba)

@app.route("/excluir", methods=["POST"])
def excluir():
    protocolo = request.form.get("protocolo")
    senha = request.form.get("senha")

    if senha != SENHA_EXCLUSAO:
        return "Senha incorreta. Exclusão não autorizada.", 403

    historico = carregar_historico()
    novo_historico = [d for d in historico if d.get("Nº Protocolo") != protocolo]

    with open(HISTORICO_PATH, "w") as f:
        json.dump(novo_historico, f, indent=4)

    return redirect("/?aba=historico")

@app.route("/exportar_pdf")
def exportar_pdf():
    historico = carregar_historico()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 120

    logo1_path = "logo1.png"
    logo2_path = "logo2.png"

    def desenhar_cabecalho():
        logo_y = height - 70
        logo_width = 100
        logo_height = 50

        if os.path.exists(logo1_path):
            pdf.drawImage(logo1_path, x=20, y=logo_y, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')

        if os.path.exists(logo2_path):
            pdf.drawImage(logo2_path, x=width - logo_width - 20, y=logo_y, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')

        pdf.setFont("Helvetica-Bold", 12)
        titulo = "Histórico de Denúncias"
        texto_largura = pdf.stringWidth(titulo, "Helvetica-Bold", 12)
        centro_x = (width - texto_largura) / 2
        pdf.drawString(centro_x, logo_y + 15, titulo)
        pdf.setFont("Helvetica", 9)

    desenhar_cabecalho()
    y -= 30

    for item in historico:
        campos = [
            f"Protocolo: {item.get('Nº Protocolo', '')}",
            f"Data: {item.get('Data Denúncia', '')}",
            f"Denunciante: {item.get('Denunciante', '')}",
            f"Tipo: {item.get('Tipo Denúncia', '')}",
            f"Local: {item.get('Local', '')}",
            f"Endereço: {item.get('Endereço', '')}",
            f"E-mail: {item.get('E-mail', '')}",
            f"Telefone: {item.get('Telefone Contato', '')}"
        ]

        for linha in campos:
            pdf.drawString(50, y, linha)
            y -= 12
            if y < 50:
                pdf.showPage()
                y = height - 120
                desenhar_cabecalho()
                y -= 30

        pdf.drawString(50, y, "-" * 80)
        y -= 15
        if y < 50:
            pdf.showPage()
            y = height - 120
            desenhar_cabecalho()
            y -= 30

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="historico_denuncias.pdf", mimetype="application/pdf")
