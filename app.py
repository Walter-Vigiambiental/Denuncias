from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import csv

app = Flask(__name__)

# Caminho do arquivo CSV de histórico
CSV_FILE = "historico.csv"

# Configuração do servidor SMTP
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER", "seuemail@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS", "suasenha")

# Senha para exclusão
SENHA_EXCLUSAO = os.getenv("SENHA_EXCLUSAO", "1234")

# ============================
# Funções auxiliares
# ============================

def enviar_email(assunto, mensagem):
    """Envia e-mail com os dados da denúncia."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_USER
        msg["Subject"] = assunto
        msg.attach(MIMEText(mensagem, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Erro ao enviar e-mail:", e)
        return False


def salvar_historico(dados):
    """Salva denúncia em CSV."""
    header = [
        "Data", "Usuário", "Tipo de Denúncia", "Tipo de Problema",
        "Outro Problema", "Local", "Endereço", "Descrição"
    ]
    arquivo_existe = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not arquivo_existe:
            writer.writeheader()
        writer.writerow(dados)


def ler_historico():
    """Lê as denúncias do CSV."""
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def limpar_historico():
    """Limpa todas as denúncias."""
    if os.path.exists(CSV_FILE):
        os.remove(CSV_FILE)


# ============================
# Rotas
# ============================

@app.route("/", methods=["GET", "POST"])
def index():
    mensagem = None
    tipo_mensagem = None

    if request.method == "POST":
        usuario = request.form.get("usuario")
        tipo_denuncia = request.form.get("tipo_denuncia")
        tipo_problema = request.form.get("tipo_problema")
        outro_problema = request.form.get("outro_problema")
        local = request.form.get("local")
        endereco = request.form.get("endereco")
        descricao = request.form.get("descricao")
        senha = request.form.get("senha_exclusao")

        # Verifica se é exclusão
        if senha:
            if senha == SENHA_EXCLUSAO:
                limpar_historico()
                mensagem = "Histórico de denúncias apagado com sucesso."
                tipo_mensagem = "sucesso"
            else:
                mensagem = "Senha incorreta. Nenhuma denúncia foi apagada."
                tipo_mensagem = "erro"
            return render_template("formulario.html", mensagem=mensagem, tipo_mensagem=tipo_mensagem)

        # Monta tipo de problema, se aplicável
        if tipo_denuncia == "Qualidade da Água":
            if tipo_problema == "Outros":
                tipo_problema = outro_problema or "Não especificado"
        else:
            tipo_problema = ""

        data = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # Cria registro
        denuncia = {
            "Data": data,
            "Usuário": usuario,
            "Tipo de Denúncia": tipo_denuncia,
            "Tipo de Problema": tipo_problema,
            "Outro Problema": outro_problema,
            "Local": local,
            "Endereço": endereco,
            "Descrição": descricao
        }

        # Salva localmente
        salvar_historico(denuncia)

        # Envia por e-mail
        assunto = f"Nova Denúncia - {tipo_denuncia}"
        corpo_email = (
            f"🕒 Data: {data}\n"
            f"👤 Usuário: {usuario}\n"
            f"📍 Local: {local}\n"
            f"🏠 Endereço: {endereco}\n"
            f"📢 Tipo de Denúncia: {tipo_denuncia}\n"
        )
        if tipo_problema:
            corpo_email += f"⚠️ Tipo de Problema: {tipo_problema}\n"
        corpo_email += f"📝 Descrição:\n{descricao}"

        if enviar_email(assunto, corpo_email):
            mensagem = "Denúncia registrada e enviada com sucesso!"
            tipo_mensagem = "sucesso"
        else:
            mensagem = "Denúncia registrada, mas ocorreu um erro ao enviar o e-mail."
            tipo_mensagem = "erro"

    return render_template("formulario.html", mensagem=mensagem, tipo_mensagem=tipo_mensagem)


@app.route("/historico")
def historico():
    denuncias = ler_historico()
    return render_template("historico.html", denuncias=denuncias)


# ============================
# Execução
# ============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
