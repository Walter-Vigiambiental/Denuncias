from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')

HISTORICO_ARQUIVO = "historico.json"
CONFIG_EMAIL = "config_email.json"
SENHA_ADMIN = "1234"  # ✅ altere para sua senha real

# --- Funções auxiliares ---
def carregar_historico():
    if not os.path.exists(HISTORICO_ARQUIVO):
        return []
    with open(HISTORICO_ARQUIVO, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def salvar_historico(data):
    with open(HISTORICO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def enviar_email(destinatario, assunto, mensagem):
    try:
        with open(CONFIG_EMAIL, "r", encoding="utf-8") as f:
            config = json.load(f)

        remetente = config["email"]
        senha = config["senha"]
        smtp_servidor = config["smtp_servidor"]
        smtp_porta = config["smtp_porta"]

        msg = MIMEText(mensagem, "html", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = remetente
        msg["To"] = destinatario

        with smtplib.SMTP(smtp_servidor, smtp_porta) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)
        print("✅ E-mail enviado com sucesso!")
        return True
    except Exception as e:
        print("❌ Erro ao enviar e-mail:", e)
        return False


# --- Rotas principais ---
@app.route("/", methods=["GET", "POST"])
def formulario():
    mensagem = None
    tipo = None

    if request.method == "POST":
        usuario = request.form.get("usuario")
        local = request.form.get("local")
        descricao = request.form.get("descricao")
        risco = request.form.get("risco")

        if not all([usuario, local, descricao, risco]):
            mensagem = "Preencha todos os campos!"
            tipo = "erro"
        else:
            novo_registro = {
                "usuario": usuario,
                "local": local,
                "descricao": descricao,
                "risco": risco,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            }

            historico = carregar_historico()
            historico.append(novo_registro)
            salvar_historico(historico)

            # envia o e-mail
            enviar_email(
                destinatario="destino@exemplo.com",  # altere conforme necessário
                assunto="Nova denúncia registrada",
                mensagem=f"""
                <h3>Nova denúncia registrada</h3>
                <b>Usuário:</b> {usuario}<br>
                <b>Local:</b> {local}<br>
                <b>Descrição:</b> {descricao}<br>
                <b>Risco:</b> {risco}<br>
                <b>Data:</b> {novo_registro['data']}
                """
            )

            mensagem = "Denúncia registrada com sucesso!"
            tipo = "sucesso"

    return render_template("formulario.html", mensagem=mensagem, tipo=tipo)


@app.route("/historico", methods=["GET", "POST"])
def historico():
    mensagem = None
    tipo = None
    senha = request.form.get("senha") if request.method == "POST" else None

    if senha:
        if senha != SENHA_ADMIN:
            mensagem = "Senha incorreta! Tente novamente."
            tipo = "erro"
            return render_template("formulario.html", mensagem=mensagem, tipo=tipo)
        else:
            historico = carregar_historico()
            return render_template("historico.html", historico=historico)

    # tela inicial da senha
    return """
    <html>
    <body style='font-family:Segoe UI; text-align:center; margin-top:100px;'>
        <h2>🔒 Acesso ao Histórico</h2>
        <form method='POST'>
            <input type='password' name='senha' placeholder='Digite a senha' required>
            <br><br>
            <button type='submit'>Entrar</button>
            <br><br>
            <a href='/' style='text-decoration:none; color:#0078D7;'>← Voltar</a>
        </form>
    </body>
    </html>
    """


@app.route("/excluir/<int:index>", methods=["POST"])
def excluir(index):
    historico = carregar_historico()
    if 0 <= index < len(historico):
        historico.pop(index)
        salvar_historico(historico)
    return redirect(url_for("historico"))


@app.route("/api/historico")
def api_historico():
    return jsonify(carregar_historico())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
