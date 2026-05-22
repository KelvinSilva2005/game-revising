import random
import time
import re
import json
import pandas as pd
import streamlit as st
from PyPDF2 import PdfReader
from groq import Groq

st.set_page_config(page_title="Game Revising", layout="wide")

POWER_UPS_PADRAO = [
    "Vale Ajuda de um Colega",
    "Vale Pular a Pergunta"
]


# =========================
# FUNÇÕES
# =========================

def validar_email(email):
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)


def aluno_label(aluno):
    return f"{aluno['nome']} ({aluno['matricula']})"


def buscar_aluno_por_label(label):
    for aluno in st.session_state.alunos:
        if aluno_label(aluno) == label:
            return aluno
    return None


def formatar_powerups(lista_powerups):
    if not lista_powerups:
        return "-"

    contagem = {}

    for power in lista_powerups:
        contagem[power] = contagem.get(power, 0) + 1

    return ", ".join(
        [f"{nome} ({qtd})" for nome, qtd in contagem.items()]
    )


def obter_groq_key():
    try:
        return st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        return ""


def extrair_json(texto):
    texto = texto.strip()
    texto = texto.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(texto)
    except Exception:
        pass

    inicio_lista = texto.find("[")
    fim_lista = texto.rfind("]")

    if inicio_lista != -1 and fim_lista != -1:
        return json.loads(texto[inicio_lista:fim_lista + 1])

    inicio_obj = texto.find("{")
    fim_obj = texto.rfind("}")

    if inicio_obj != -1 and fim_obj != -1:
        return json.loads(texto[inicio_obj:fim_obj + 1])

    raise ValueError("Não foi possível encontrar JSON válido.")


# =========================
# IA SIMULADA
# =========================

def gerar_perguntas_simuladas(qtd):
    perguntas = []

    for i in range(1, qtd + 1):
        perguntas.append({
            "id": i,
            "pergunta": f"Pergunta {i}: escolha a alternativa correta sobre o conteúdo da matéria.",
            "alternativas": {
                "A": "Alternativa correta relacionada ao conteúdo.",
                "B": "Alternativa incorreta.",
                "C": "Alternativa parcialmente incorreta.",
                "D": "Alternativa fora do contexto."
            },
            "correta": "A"
        })

    return perguntas


def normalizar_perguntas(dados):

    if isinstance(dados, dict):
        dados = dados.get("perguntas", [])

    perguntas = []

    for i, item in enumerate(dados, start=1):

        alternativas = item.get("alternativas", {})

        perguntas.append({
            "id": i,
            "pergunta": item.get("pergunta", f"Pergunta {i}"),
            "alternativas": {
                "A": alternativas.get("A", ""),
                "B": alternativas.get("B", ""),
                "C": alternativas.get("C", ""),
                "D": alternativas.get("D", "")
            },
            "correta": item.get("correta", "A")
        })

    return perguntas


# =========================
# IA GROQ
# =========================

def gerar_perguntas_ia(texto_pdf, quantidade):

    api_key = obter_groq_key()

    if not api_key:
        st.warning("Sem chave da Groq. Usando modo simulado.")
        return gerar_perguntas_simuladas(quantidade)

    if not texto_pdf.strip():
        st.warning("PDF vazio.")
        return gerar_perguntas_simuladas(quantidade)

    try:

        client = Groq(api_key=api_key)

        prompt = f"""
Crie exatamente {quantidade} perguntas de múltipla escolha.

Responda SOMENTE em JSON válido.

Formato:
{{
 "perguntas":[
   {{
     "id":1,
     "pergunta":"...",
     "alternativas":{{
       "A":"...",
       "B":"...",
       "C":"...",
       "D":"..."
     }},
     "correta":"A"
   }}
 ]
}}

Baseie-se SOMENTE neste conteúdo:

{texto_pdf[:12000]}
"""

        resposta = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "Você responde apenas JSON válido."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        texto = resposta.choices[0].message.content

        dados = extrair_json(texto)

        perguntas = normalizar_perguntas(dados)

        if perguntas:
            return perguntas

        raise ValueError("JSON vazio")

    except Exception as e:

        st.warning("Erro na Groq. Usando modo simulado.")
        st.caption(f"Motivo técnico: {e}")

        return gerar_perguntas_simuladas(quantidade)


# =========================
# SESSION STATE
# =========================

if "usuarios" not in st.session_state:
    st.session_state.usuarios = {
        "professor@email.com": {
            "senha": "1234"
        }
    }

if "logado" not in st.session_state:
    st.session_state.logado = False

if "usuario" not in st.session_state:
    st.session_state.usuario = ""

if "alunos" not in st.session_state:
    st.session_state.alunos = []

if "scores" not in st.session_state:
    st.session_state.scores = {}

if "powerups" not in st.session_state:
    st.session_state.powerups = {}

if "acertos" not in st.session_state:
    st.session_state.acertos = {}

if "questions" not in st.session_state:
    st.session_state.questions = []

if "used_questions" not in st.session_state:
    st.session_state.used_questions = []

if "texto_pdf" not in st.session_state:
    st.session_state.texto_pdf = ""

if "resumo_pdf" not in st.session_state:
    st.session_state.resumo_pdf = ""

if "current_question" not in st.session_state:
    st.session_state.current_question = None

if "victim" not in st.session_state:
    st.session_state.victim = None

if "tempo" not in st.session_state:
    st.session_state.tempo = 30

if "ranking_final" not in st.session_state:
    st.session_state.ranking_final = False

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Dashboard"

if "usar_ajuda" not in st.session_state:
    st.session_state.usar_ajuda = False

if "aluno_auxiliar" not in st.session_state:
    st.session_state.aluno_auxiliar = None


# =========================
# LOGIN
# =========================

def tela_login():

    st.title("🎮 Game Revising")

    aba1, aba2, aba3 = st.tabs(
        ["Login", "Cadastrar Professor", "Esqueci a Senha"]
    )

    with aba1:

        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")

        if st.button("Entrar"):

            if email in st.session_state.usuarios and \
               st.session_state.usuarios[email]["senha"] == senha:

                st.session_state.logado = True
                st.session_state.usuario = email
                st.rerun()

            else:
                st.error("Login inválido.")

    with aba2:

        novo_email = st.text_input("Novo e-mail")
        nova_senha = st.text_input("Nova senha", type="password")

        if st.button("Cadastrar Professor"):

            st.session_state.usuarios[novo_email] = {
                "senha": nova_senha
            }

            st.success("Professor cadastrado.")

    with aba3:

        email_rec = st.text_input("Digite seu e-mail")

        if st.button("Recuperar Senha"):

            if email_rec in st.session_state.usuarios:
                st.info(
                    f"Senha: {st.session_state.usuarios[email_rec]['senha']}"
                )
            else:
                st.error("E-mail não encontrado.")


if not st.session_state.logado:
    tela_login()
    st.stop()


# =========================
# SIDEBAR
# =========================

st.sidebar.title("🎮 Game Revising")

paginas = [
    "Dashboard",
    "Alunos",
    "PDF da Matéria",
    "Perguntas",
    "Jogo",
    "Ranking"
]

pagina = st.sidebar.radio(
    "Menu",
    paginas,
    index=paginas.index(st.session_state.pagina_atual)
)

st.session_state.pagina_atual = pagina


# =========================
# DASHBOARD
# =========================

if pagina == "Dashboard":

    st.title("📊 Dashboard")

    col1, col2, col3 = st.columns(3)

    col1.metric("Alunos", len(st.session_state.alunos))
    col2.metric("Perguntas", len(st.session_state.questions))
    col3.metric("Tempo", f"{st.session_state.tempo}s")


# =========================
# ALUNOS
# =========================

elif pagina == "Alunos":

    st.title("👥 Alunos")

    nome = st.text_input("Nome")
    matricula = st.text_input("Matrícula")

    powerups_iniciais = st.multiselect(
        "Power-ups iniciais",
        POWER_UPS_PADRAO
    )

    if st.button("Adicionar aluno"):

        aluno = {
            "nome": nome,
            "matricula": matricula
        }

        st.session_state.alunos.append(aluno)

        st.session_state.scores[matricula] = 0
        st.session_state.powerups[matricula] = powerups_iniciais.copy()
        st.session_state.acertos[matricula] = 0

        st.success("Aluno cadastrado.")

    st.divider()

    st.subheader("Importar CSV")

    arquivo = st.file_uploader(
        "Enviar CSV",
        type=["csv"]
    )

    if arquivo:

        df = pd.read_csv(arquivo)

        for _, row in df.iterrows():

            nome_csv = str(row["nome"])
            matricula_csv = str(row["matricula"])

            aluno = {
                "nome": nome_csv,
                "matricula": matricula_csv
            }

            st.session_state.alunos.append(aluno)

            st.session_state.scores[matricula_csv] = 0
            st.session_state.powerups[matricula_csv] = []
            st.session_state.acertos[matricula_csv] = 0

        st.success("CSV importado.")

    st.divider()

    st.subheader("Lista de alunos")

    dados = []

    for aluno in st.session_state.alunos:

        mat = aluno["matricula"]

        dados.append({
            "Nome": aluno["nome"],
            "Matrícula": mat,
            "Pontos": st.session_state.scores.get(mat, 0),
            "Acertos": st.session_state.acertos.get(mat, 0),
            "Power-ups": formatar_powerups(
                st.session_state.powerups.get(mat, [])
            )
        })

    if dados:
        st.dataframe(pd.DataFrame(dados), use_container_width=True)


# =========================
# PDF
# =========================

elif pagina == "PDF da Matéria":

    st.title("📄 PDF")

    pdf = st.file_uploader("Enviar PDF", type=["pdf"])

    if pdf:

        reader = PdfReader(pdf)

        texto = ""

        for page in reader.pages:
            texto += page.extract_text() or ""

        st.session_state.texto_pdf = texto
        st.session_state.resumo_pdf = texto[:1500]

        st.success("PDF carregado.")

        st.subheader("Resumo do PDF")

        st.text_area(
            "Resumo",
            st.session_state.resumo_pdf,
            height=250
        )


# =========================
# PERGUNTAS
# =========================

elif pagina == "Perguntas":

    st.title("📝 Perguntas")

    modo = st.radio(
        "Modo de criação",
        ["Gerar com IA", "Criar manualmente"]
    )

    # IA
    if modo == "Gerar com IA":

        quantidade = st.number_input(
            "Quantidade de perguntas",
            min_value=1,
            max_value=20,
            value=5
        )

        if st.button("Gerar perguntas com IA"):

            perguntas = gerar_perguntas_ia(
                st.session_state.texto_pdf,
                quantidade
            )

            st.session_state.questions = perguntas
            st.session_state.used_questions = []

            st.success("Perguntas geradas.")

    # MANUAL
    else:

        pergunta = st.text_area("Pergunta")

        a = st.text_input("Alternativa A")
        b = st.text_input("Alternativa B")
        c = st.text_input("Alternativa C")
        d = st.text_input("Alternativa D")

        correta = st.selectbox(
            "Resposta correta",
            ["A", "B", "C", "D"]
        )

        if st.button("Adicionar pergunta"):

            nova = {
                "id": len(st.session_state.questions) + 1,
                "pergunta": pergunta,
                "alternativas": {
                    "A": a,
                    "B": b,
                    "C": c,
                    "D": d
                },
                "correta": correta
            }

            st.session_state.questions.append(nova)

            st.success("Pergunta adicionada.")

    st.divider()

    st.subheader("Perguntas cadastradas")

    for q in st.session_state.questions:

        st.write(f"### {q['pergunta']}")

        st.write(f"A) {q['alternativas']['A']}")
        st.write(f"B) {q['alternativas']['B']}")
        st.write(f"C) {q['alternativas']['C']}")
        st.write(f"D) {q['alternativas']['D']}")

        st.write(f"✅ Correta: {q['correta']}")

        st.divider()


# =========================
# JOGO
# =========================

elif pagina == "Jogo":

    st.title("▶️ Play / Jogo")

    if not st.session_state.alunos:
        st.warning("Cadastre alunos antes de jogar.")
        st.stop()

    if not st.session_state.questions:
        st.warning("Crie perguntas antes de jogar.")
        st.stop()

    st.session_state.tempo = st.number_input(
        "Configurar tempo do cronômetro",
        min_value=10,
        max_value=300,
        value=st.session_state.tempo
    )

    labels = [aluno_label(a) for a in st.session_state.alunos]

    aluno_escolhido_label = st.selectbox(
        "Escolha o aluno que vai responder",
        labels
    )

    aluno_escolhido = buscar_aluno_por_label(aluno_escolhido_label)
    mat = aluno_escolhido["matricula"]

    st.subheader("Power-ups disponíveis")

    st.info(
        formatar_powerups(
            st.session_state.powerups.get(mat, [])
        )
    )

    st.divider()

    if st.button("PLAY"):

        perguntas_disponiveis = [
            q for q in st.session_state.questions
            if q["id"] not in st.session_state.used_questions
        ]

        if perguntas_disponiveis:

            st.session_state.current_question = random.choice(
                perguntas_disponiveis
            )

            st.session_state.used_questions.append(
                st.session_state.current_question["id"]
            )

            st.session_state.victim = aluno_escolhido

            st.session_state.usar_ajuda = False
            st.session_state.aluno_auxiliar = None

            st.success(
                f"Pergunta carregada para {aluno_label(aluno_escolhido)}."
            )

        else:
            st.warning("Todas as perguntas já foram usadas.")

    if not st.session_state.current_question:
        st.info("Clique em PLAY para carregar a pergunta.")
        st.stop()

    q = st.session_state.current_question

    st.metric(
        "Aluno respondendo",
        aluno_label(st.session_state.victim)
    )

    st.subheader("Pergunta")

    st.info(q["pergunta"])

    st.write(f"**A)** {q['alternativas']['A']}")
    st.write(f"**B)** {q['alternativas']['B']}")
    st.write(f"**C)** {q['alternativas']['C']}")
    st.write(f"**D)** {q['alternativas']['D']}")

    with st.expander("Gabarito do professor"):

        correta = q["correta"]

        st.success(
            f"Resposta correta: {correta}) {q['alternativas'][correta]}"
        )

    st.divider()

    st.subheader("Power-ups desta pergunta")

    mat_resposta = st.session_state.victim["matricula"]

    powerups_aluno = st.session_state.powerups.get(
        mat_resposta,
        []
    )

    colp1, colp2 = st.columns(2)

    with colp1:

        st.session_state.usar_ajuda = st.checkbox(
            "Usar Vale Ajuda de um Colega",
            value=st.session_state.usar_ajuda,
            disabled="Vale Ajuda de um Colega" not in powerups_aluno
        )

        usar_ajuda = st.session_state.usar_ajuda

    aluno_auxiliar = None

    if usar_ajuda:

        alunos_auxiliares = [
            aluno_label(a)
            for a in st.session_state.alunos
            if a["matricula"] != mat_resposta
        ]

        if alunos_auxiliares:

            auxiliar_label = st.selectbox(
                "Escolha o colega que vai ajudar",
                alunos_auxiliares
            )

            aluno_auxiliar = buscar_aluno_por_label(
                auxiliar_label
            )

            st.session_state.aluno_auxiliar = aluno_auxiliar

    with colp2:

        if st.button("Usar Vale Pular a Pergunta"):

            if "Vale Pular a Pergunta" in powerups_aluno:

                st.session_state.powerups[mat_resposta].remove(
                    "Vale Pular a Pergunta"
                )

                perguntas_disponiveis = [
                    pergunta for pergunta in st.session_state.questions
                    if pergunta["id"] not in st.session_state.used_questions
                ]

                if perguntas_disponiveis:

                    proxima = random.choice(
                        perguntas_disponiveis
                    )

                    st.session_state.current_question = proxima

                    st.session_state.used_questions.append(
                        proxima["id"]
                    )

                    st.session_state.usar_ajuda = False
                    st.session_state.aluno_auxiliar = None

                    st.success(
                        "Pergunta pulada."
                    )

                    st.rerun()

                else:
                    st.warning("Não há mais perguntas.")

            else:
                st.warning("Sem esse power-up.")

    st.divider()

    if st.button("Rodar cronômetro"):

        contador = st.empty()

        for t in range(
            int(st.session_state.tempo),
            -1,
            -1
        ):

            contador.metric(
                "Tempo restante",
                f"{t}s"
            )

            time.sleep(1)

        st.warning("Tempo encerrado.")

    resposta = st.radio(
        "Alternativa respondida",
        ["A", "B", "C", "D"],
        horizontal=True
    )

    c1, c2, c3 = st.columns(3)

    if c1.button("✅ Confirmar resposta"):

        aluno = st.session_state.victim
        mat = aluno["matricula"]

        if resposta == q["correta"]:

            st.session_state.scores[mat] += 1

            st.session_state.acertos[mat] = \
                st.session_state.acertos.get(mat, 0) + 1

            mensagem = f"""
Correto! {aluno_label(aluno)} ganhou 1 ponto.
"""

            if st.session_state.usar_ajuda and st.session_state.aluno_auxiliar:

                mat_aux = st.session_state.aluno_auxiliar["matricula"]

                st.session_state.scores[mat_aux] = \
                    st.session_state.scores.get(mat_aux, 0) + 0.5

                if "Vale Ajuda de um Colega" in \
                   st.session_state.powerups.get(mat, []):

                    st.session_state.powerups[mat].remove(
                        "Vale Ajuda de um Colega"
                    )

                mensagem += f"""
{aluno_label(st.session_state.aluno_auxiliar)}
ganhou 0.5 ponto pela ajuda.
"""

            if st.session_state.acertos[mat] % 3 == 0:

                novo_power = random.choice(
                    POWER_UPS_PADRAO
                )

                st.session_state.powerups[mat].append(
                    novo_power
                )

                mensagem += f"""
Também recebeu o power-up:
{novo_power}
"""

            st.success(mensagem)

        else:

            st.session_state.scores[mat] -= 0.5

            st.error("Resposta errada.")

            if st.session_state.usar_ajuda and \
               "Vale Ajuda de um Colega" in \
               st.session_state.powerups.get(mat, []):

                st.session_state.powerups[mat].remove(
                    "Vale Ajuda de um Colega"
                )

                st.warning("O Vale Ajuda de um Colega foi consumido.")

        perguntas_disponiveis = [
            pergunta for pergunta in st.session_state.questions
            if pergunta["id"] not in st.session_state.used_questions
        ]

        if perguntas_disponiveis:

            proxima = random.choice(
                perguntas_disponiveis
            )

            st.session_state.current_question = proxima

            st.session_state.used_questions.append(
                proxima["id"]
            )

            st.session_state.usar_ajuda = False
            st.session_state.aluno_auxiliar = None

            st.info(
                "Próxima pergunta carregada."
            )

            st.rerun()

        else:

            st.session_state.current_question = None

            st.session_state.usar_ajuda = False
            st.session_state.aluno_auxiliar = None

            st.warning(
                "Todas as perguntas foram respondidas."
            )

    if c2.button("Editar pergunta"):

        st.session_state.pagina_atual = "Perguntas"

        st.rerun()

    if c3.button("Ir para Ranking"):

        st.session_state.ranking_final = True

        st.session_state.pagina_atual = "Ranking"

        st.rerun()

    st.divider()

    if st.button("Reiniciar rodada"):

        st.session_state.current_question = None
        st.session_state.victim = None
        st.session_state.usar_ajuda = False
        st.session_state.aluno_auxiliar = None

        st.success("Rodada reiniciada.")


# =========================
# RANKING
# =========================

elif pagina == "Ranking":

    st.title("🏆 Ranking Final")

    dados = []

    for aluno in st.session_state.alunos:

        mat = aluno["matricula"]

        dados.append({
            "Nome": aluno["nome"],
            "Matrícula": mat,
            "Pontos": st.session_state.scores.get(mat, 0),
            "Acertos": st.session_state.acertos.get(mat, 0),
            "Power-ups": formatar_powerups(
                st.session_state.powerups.get(mat, [])
            )
        })

    ranking = pd.DataFrame(dados)

    if not ranking.empty:

        ranking = ranking.sort_values(
            "Pontos",
            ascending=False
        )

        st.dataframe(
            ranking,
            use_container_width=True
        )

    if st.button("Resetar jogo"):

        st.session_state.scores = {
            a["matricula"]: 0
            for a in st.session_state.alunos
        }

        st.session_state.powerups = {
            a["matricula"]: []
            for a in st.session_state.alunos
        }

        st.session_state.acertos = {
            a["matricula"]: 0
            for a in st.session_state.alunos
        }

        st.session_state.used_questions = []
        st.session_state.current_question = None
        st.session_state.victim = None
        st.session_state.usar_ajuda = False
        st.session_state.aluno_auxiliar = None

        st.success("Jogo resetado.")