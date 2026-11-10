"""
Rotina de tratamento dos dados da Lei Estadual de Incentivo ao Esporte de Minas Gerais (LEIE/MG).

Trabalho de Conclusão de Curso (UFMG/EEFFTO) de Daniel Resende Dias.
Reproduz os números do TCC a partir das duas planilhas fornecidas pela SEDESE:

  - base de projetos, posição de 08/05/2025 (Minas Gerais, 2025a);
  - base de Termos de Compromisso (TC), posição de março de 2025 (Minas Gerais, 2025b).

As planilhas NÃO estão no repositório, porque trazem dados de contato pessoal
(representante legal, e-mail e telefone). Esses campos são descartados já na leitura.

Uso:
    python rotina_leie_mg.py --projetos <planilha de projetos.xlsx> \
                             --termos <planilha de termos.xlsx> \
                             [--saida resultados]

As etapas seguem a numeração do Apêndice D do TCC.
"""

import argparse
import re
from pathlib import Path

import pandas as pd

AUX = Path(__file__).resolve().parent / "dados_auxiliares"

# Campos de contato pessoal: nunca são lidos para a análise.
CAMPOS_PESSOAIS = ["Representante legal", "E-mail", "Telefone"]

COL_APROVADO = "Valor aprovado (se aprovado) / previsto (se indeferido)"
ANOS = list(range(2014, 2026))
COL_ANOS = [f"Valor captado {a}" for a in ANOS]
COL_MUN = "Município(s) de execução"

# Unilever aparece com duas raízes de CNPJ; é tratada como uma só empresa.
RAIZES_MESMA_EMPRESA = {"01615814": "61068276"}


# ---------------------------------------------------------------------------
# Etapa 1: leitura das planilhas, sem os campos de contato pessoal
# ---------------------------------------------------------------------------
def ler_bases(arq_projetos, arq_termos):
    proj = pd.read_excel(
        arq_projetos,
        sheet_name="projetos_Lei_Incentivo (2)",
        header=1,
        usecols=lambda c: c not in CAMPOS_PESSOAIS,
    )
    termos = pd.read_excel(arq_termos, sheet_name="Captacao ANO A ANO")
    termos = termos.drop(columns=[c for c in CAMPOS_PESSOAIS if c in termos.columns])
    return proj, termos


# ---------------------------------------------------------------------------
# Etapa 2: remoção das linhas de totalização (sem número de projeto)
# ---------------------------------------------------------------------------
def remover_totalizacao(proj):
    sem_numero = proj["Número projeto"].isna()
    print(f"[2] linhas de totalização removidas: {sem_numero.sum()}")
    proj = proj[~sem_numero].copy()
    for c in [COL_APROVADO, "Total captado"] + COL_ANOS:
        # Uma célula de 2023 está como texto ("R$ 25.000,00" com tabulação) e
        # vira vazio aqui, como na análise do TCC.
        proj[c] = pd.to_numeric(proj[c], errors="coerce")
    proj["captado"] = proj[COL_ANOS].sum(axis=1)
    return proj


# ---------------------------------------------------------------------------
# Etapa 3: padronização das categorias
# ---------------------------------------------------------------------------
def padronizar_categorias(proj):
    tipos = pd.read_csv(AUX / "tipos_executor.csv")
    mapa = dict(zip(tipos["rotulo_original"], tipos["categoria"]))
    rotulo = proj["Tipo Executor"].astype(str).str.strip().str.lower()
    proj["tipo"] = rotulo.map(mapa)
    sem_tipo = proj.loc[proj["tipo"].isna(), "Tipo Executor"].unique()
    if len(sem_tipo):
        raise ValueError(f"Rótulos de tipo de executor sem categoria: {sem_tipo}")
    print(f"[3] rótulos de tipo de executor: {rotulo.nunique()} -> {proj['tipo'].nunique()} categorias")

    dim = proj["Dimensão esportiva"].astype(str).str.strip()
    dim = dim.replace({"Desenvolvimento Científico- Tecnológico": "Desenvolvimento Científico-Tecnológico"})
    proj["dimensao"] = dim
    proj["ano_edital"] = proj["Edital"].astype(str).str[:4].astype(int)
    proj["cnpj_executor"] = (
        proj["CNPJ Executor"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14)
    )
    return proj


# ---------------------------------------------------------------------------
# Etapa 4: padronização do número do projeto e dos CNPJs nos Termos
# ---------------------------------------------------------------------------
def normalizar_numero_projeto(valor):
    s = re.sub(r"\s", "", str(valor))
    if re.fullmatch(r"\d{10}", s):  # 2024080031 -> 2024.08.0031
        s = f"{s[:4]}.{s[4:6]}.{s[6:]}"
    return s


def normalizar_cnpj(valor):
    """Devolve o CNPJ com 14 dígitos.

    Quando o CNPJ vem formatado (NN.NNN.NNN/NNNN-NN), cada parte é completada
    com zeros à esquerda. Isso corrige, por exemplo, uma filial digitada com
    três dígitos ("/066-"). Quando vem como número, sem formatação, os zeros
    iniciais perdidos na planilha são recolocados (6981180000116 -> 06981180000116).
    """
    s = str(valor).strip()
    m = re.match(r"^(\d{1,2})\.(\d{3})\.(\d{3})/(\d{1,4})-(\d{2})$", s)
    if m:
        return m[1].zfill(2) + m[2] + m[3] + m[4].zfill(4) + m[5]
    return re.sub(r"\D", "", s).zfill(14)


def padronizar_termos(termos):
    bruto = termos["Número Projeto"].astype(str)
    termos["n_sem_pontos"] = int((~bruto.str.contains(r"\.")).sum())
    termos["n_com_espacos"] = int((bruto != bruto.str.strip()).sum())
    termos["projeto"] = bruto.map(normalizar_numero_projeto)
    # Um termo traz o valor como texto ("R$ 5.000,00") e é tratado como sem valor.
    termos["valor"] = pd.to_numeric(termos["Valor do TC"], errors="coerce").fillna(0)
    termos["cnpj"] = termos["CNPJ"].map(normalizar_cnpj)
    termos["raiz"] = termos["cnpj"].str[:8].replace(RAIZES_MESMA_EMPRESA)
    return termos


# ---------------------------------------------------------------------------
# Etapa 5: separação dos municípios de execução e correção de grafias
# ---------------------------------------------------------------------------
def separar_municipios(proj):
    corr = pd.read_csv(AUX / "correcoes_municipios.csv")
    corr = dict(zip(corr["grafia_base"], corr["grafia_ibge"]))

    def dividir(texto):
        if pd.isna(texto):
            return []
        partes = re.split(r"\s*/\s*|;|,|\n", str(texto))
        nomes = [p.strip(" .-").upper() for p in partes]
        return sorted({corr.get(n, n) for n in nomes if n})

    proj["municipios"] = proj[COL_MUN].map(dividir)
    return proj


# ---------------------------------------------------------------------------
# Etapa 6: projetos habilitados à captação
# ---------------------------------------------------------------------------
def habilitados(proj):
    status = proj["Status"].astype(str).str.strip()
    hab = proj[~status.isin(["Indeferidos", "Análise"])].copy()
    print(f"[6] projetos: {len(proj)}; indeferidos: {(status == 'Indeferidos').sum()}; "
          f"em análise: {(status == 'Análise').sum()}; habilitados: {len(hab)}")
    return hab


# ---------------------------------------------------------------------------
# Etapa 7: cruzamento das bases pelo número do projeto
# ---------------------------------------------------------------------------
def cruzar(proj, termos):
    existe = termos["projeto"].isin(set(proj["Número projeto"].astype(str).str.strip()))
    return existe


# ---------------------------------------------------------------------------
# Etapa 8: consolidação dos apoiadores (empresas, grupos e setores)
# ---------------------------------------------------------------------------
def consolidar_apoiadores(termos):
    nomes = (
        termos.groupby(["raiz", "Nome do Apoiador"]).size().reset_index(name="n")
        .sort_values(["raiz", "n"], ascending=[True, False])
        .drop_duplicates("raiz").set_index("raiz")["Nome do Apoiador"]
    )
    emp = termos.groupby("raiz").agg(termos=("valor", "size"), valor=("valor", "sum"))
    emp["empresa"] = nomes.str.strip()
    emp = emp.sort_values("valor", ascending=False)

    setores = pd.read_csv(AUX / "setores.csv", dtype={"raiz_cnpj": str})
    emp["setor"] = emp.index.map(dict(zip(setores["raiz_cnpj"], setores["setor"])))
    if emp["setor"].isna().any():
        faltam = emp[emp["setor"].isna()][["empresa"]]
        raise ValueError(f"Empresas sem setor em setores.csv:\n{faltam}")

    grupos = pd.read_csv(AUX / "grupos_economicos.csv", dtype={"raiz_cnpj": str})
    emp["grupo"] = emp.index.map(dict(zip(grupos["raiz_cnpj"], grupos["grupo"])))
    return emp


# ---------------------------------------------------------------------------
# Etapa 9: município sede dos executores e mesorregiões
# ---------------------------------------------------------------------------
def localizar(hab):
    sedes = pd.read_csv(AUX / "sedes_executores.csv", dtype={"cnpj_executor": str, "codigo_ibge": str})
    ibge = pd.read_csv(AUX / "municipios_mg_ibge.csv", dtype={"codigo_ibge": str})
    ibge["nome"] = ibge["municipio"].str.upper()
    meso_por_nome = dict(zip(ibge["nome"], ibge["mesorregiao"]))
    meso_por_codigo = dict(zip(ibge["codigo_ibge"], ibge["mesorregiao"]))
    nome_por_codigo = dict(zip(ibge["codigo_ibge"], ibge["nome"]))

    hab["sede_codigo"] = hab["cnpj_executor"].map(dict(zip(sedes["cnpj_executor"], sedes["codigo_ibge"])))
    hab["sede"] = hab["sede_codigo"].map(nome_por_codigo)
    hab["sede_meso"] = hab["sede_codigo"].map(meso_por_codigo)
    hab["mun_mg"] = hab["municipios"].map(lambda ms: [m for m in ms if m in meso_por_nome])
    hab["mun_fora"] = hab["municipios"].map(lambda ms: [m for m in ms if m not in meso_por_nome])
    hab["meso_exec"] = hab["mun_mg"].map(lambda ms: sorted({meso_por_nome[m] for m in ms}))
    return hab, ibge


# ---------------------------------------------------------------------------
# Etapa 10: verificações de consistência e tabelas
# ---------------------------------------------------------------------------
def pct(a, b):
    return round(100 * a / b, 1) if b else None


def quadro1(proj, termos, existe):
    q = {}
    soma = proj[COL_ANOS].sum(axis=1)
    q["total captado = soma dos anos"] = int((abs(proj["Total captado"].fillna(0) - soma) < 0.01).sum())
    q["valores negativos"] = int((proj[[COL_APROVADO] + COL_ANOS] < 0).sum().sum())
    q["dimensão em branco"] = int(proj["Dimensão esportiva"].isna().sum())
    exc = (proj["captado"] - proj[COL_APROVADO]).round(2)  # arredonda ao centavo
    q["projetos com captação acima do aprovado"] = int((exc > 0).sum())
    q["excesso total (R$)"] = round(exc[exc > 0].sum(), 2)
    q["excesso acima de 0,1% do aprovado"] = int((exc > 0.001 * proj[COL_APROVADO]).sum())
    dobro = (abs(proj["captado"] - 2 * proj[COL_APROVADO]) < 0.01) & (proj[COL_APROVADO] > 0)
    q["captação igual ao dobro do aprovado"] = int(dobro.sum())
    st = proj["Status"].astype(str).str.strip()
    for nome, rot in [("indeferidos", "Indeferidos"), ("em análise", "Análise")]:
        sel = (st == rot) & (proj["captado"] > 0)
        q[f"{nome} com captação (projetos)"] = int(sel.sum())
        q[f"{nome} com captação (R$)"] = round(proj.loc[sel, "captado"].sum(), 2)
    q["número de projeto repetido"] = int(proj["Número projeto"].duplicated().sum())
    q["termos com número sem pontos"] = int(termos["n_sem_pontos"].iloc[0])
    q["termos com espaços no número"] = int(termos["n_com_espacos"].iloc[0])
    q["termos com projeto inexistente"] = int((~existe).sum())
    q["valor desses termos (R$)"] = round(termos.loc[~existe, "valor"].sum(), 2)
    q["termos sem valor numérico"] = int(pd.to_numeric(termos["Valor do TC"], errors="coerce").isna().sum())
    q["divergência entre as bases (R$)"] = round(proj["captado"].sum() - termos["valor"].sum(), 2)
    q["  dessa, no exercício de 2025 (R$)"] = round(
        proj["Valor captado 2025"].sum() - termos.loc[termos["Ano captação"] == 2025, "valor"].sum(), 2)
    return pd.Series(q, name="resultado")


def tabelas(proj, hab, termos, emp, ibge):
    T = {}
    hab["captou"] = hab["captado"] > 0
    cap = hab[hab["captou"]]

    # Tabela 2: aprovado por ano do edital; captado por ano; limite anual
    lim = pd.read_csv(AUX / "limite_anual.csv").set_index("ano")["limite"]
    t2 = pd.DataFrame(index=range(2013, 2026))
    t2["aprovado"] = hab.groupby("ano_edital")[COL_APROVADO].sum()
    t2["captado"] = pd.Series({a: hab[f"Valor captado {a}"].sum() for a in ANOS})
    t2["limite"] = lim
    t2["pct_limite"] = (100 * t2["captado"] / t2["limite"]).round(1)
    T["tabela02_evolucao_anual"] = t2

    # Tabela 3: por dimensão esportiva
    g = hab.groupby("dimensao")
    t3 = pd.DataFrame({"habilitados": g.size(), "captaram": g["captou"].sum(),
                       "valor_captado": g["captado"].sum()})
    t3["pct_captaram"] = (100 * t3["captaram"] / t3["habilitados"]).round(1)
    t3["pct_valor"] = (100 * t3["valor_captado"] / t3["valor_captado"].sum()).round(1)
    T["tabela03_dimensoes"] = t3.sort_values("valor_captado", ascending=False)

    # Tabela 4: conversão entre aprovação e captação
    t4 = pd.DataFrame({"aprovado": g[COL_APROVADO].sum(), "captado": g["captado"].sum()})
    t4["pct_do_aprovado"] = (100 * t4["captado"] / t4["aprovado"]).round(1)
    gc = cap.groupby("dimensao")
    t4["pct_do_aprovado_so_quem_captou"] = (100 * gc["captado"].sum() / gc[COL_APROVADO].sum()).round(1)
    T["tabela04_conversao"] = t4.sort_values("pct_do_aprovado", ascending=False)

    # Gráfico 1: projetos que captaram, por dimensão e ano
    T["grafico01_projetos_por_dimensao_ano"] = pd.DataFrame(
        {a: hab[hab[f"Valor captado {a}"] > 0].groupby("dimensao").size() for a in ANOS}
    ).fillna(0).astype(int)

    # Tabela 5: por tipo de executor
    g = hab.groupby("tipo")
    t5 = pd.DataFrame({"habilitados": g.size(), "captaram": g["captou"].sum(),
                       "valor_captado": g["captado"].sum()})
    t5["pct_captaram"] = (100 * t5["captaram"] / t5["habilitados"]).round(1)
    t5["pct_valor"] = (100 * t5["valor_captado"] / t5["valor_captado"].sum()).round(1)
    T["tabela05_tipo_executor"] = t5.sort_values("valor_captado", ascending=False)

    # Tabela 6: dez maiores executores
    g = cap.groupby("cnpj_executor")
    t6 = pd.DataFrame({"executor": g["Nome Executor"].first(), "sede": g["sede"].first(),
                       "projetos": g.size(), "aprovado": g[COL_APROVADO].sum(),
                       "captado": g["captado"].sum()})
    T["tabela06_maiores_executores"] = t6.sort_values("captado", ascending=False).head(10)

    # Tabela 7: dez maiores empresas
    T["tabela07_maiores_empresas"] = emp[["empresa", "termos", "valor"]].head(10)

    # Tabela 8: após agrupamento por grupo econômico
    chave = emp["grupo"].fillna(emp["empresa"])
    t8 = emp.groupby(chave)["valor"].sum().sort_values(ascending=False)
    T["tabela08_grupos"] = t8.head(10).to_frame()

    # Tabela 9: por setor de atividade
    t9 = emp.groupby("setor").agg(empresas=("valor", "size"), valor=("valor", "sum"))
    t9["pct_empresas"] = (100 * t9["empresas"] / t9["empresas"].sum()).round(1)
    t9["pct_valor"] = (100 * t9["valor"] / t9["valor"].sum()).round(1)
    T["tabela09_setores"] = t9.sort_values("valor", ascending=False)

    # Tabela 10: municípios com mais projetos executados e valor pela sede
    exec_mun = cap.explode("mun_mg")["mun_mg"].value_counts()
    g = cap.groupby("sede")
    t10 = pd.DataFrame({"projetos_executados": exec_mun,
                        "executores_sediados": g["cnpj_executor"].nunique(),
                        "valor_executores_sediados": g["captado"].sum()}).fillna(0)
    t10 = t10.rename_axis("municipio").reset_index()
    t10 = t10.sort_values(["projetos_executados", "municipio"], ascending=[False, True])
    T["tabela10_municipios"] = t10.set_index("municipio").head(10)

    # Tabela 11: por mesorregião
    tot_meso = ibge.groupby("mesorregiao").size()
    nomes_meso = dict(zip(ibge["nome"], ibge["mesorregiao"]))
    com_proj = pd.Series([nomes_meso[m] for m in exec_mun.index]).value_counts()
    proj_meso = cap.explode("meso_exec")["meso_exec"].value_counts()
    val_meso = cap.groupby("sede_meso")["captado"].sum()
    t11 = pd.DataFrame({"municipios": tot_meso, "municipios_com_projetos": com_proj,
                        "projetos_executados": proj_meso, "valor_sede": val_meso}).fillna(0)
    t11["cobertura_pct"] = (100 * t11["municipios_com_projetos"] / t11["municipios"]).round(1)
    t11["pct_valor"] = (100 * t11["valor_sede"] / cap["captado"].sum()).round(1)
    T["tabela11_mesorregioes"] = t11.sort_values("valor_sede", ascending=False)

    # Tabela 12 (Apêndice B): empresas dos grupos econômicos
    T["tabela12_grupos_detalhe"] = emp[emp["grupo"].notna()][["grupo", "empresa", "termos", "valor"]] \
        .sort_values(["grupo", "valor"], ascending=[True, False])

    # Tabela 13 (Apêndice C): municípios com projetos que captaram
    t13 = exec_mun.rename("projetos").to_frame()
    t13["mesorregiao"] = t13.index.map(nomes_meso)
    T["tabela13_municipios"] = t13

    return T


def indicadores(proj, hab, termos, emp, T):
    """Números citados no texto do TCC."""
    cap = hab[hab["captado"] > 0]
    st = proj["Status"].astype(str).str.strip()
    v = emp["valor"]
    n20 = round(0.2 * len(emp))
    multi = cap["municipios"].map(len)
    fora = cap["mun_fora"].map(len) > 0
    so_fora = cap["mun_mg"].map(len) == 0
    na_sede = cap.apply(lambda r: r["sede"] in r["mun_mg"], axis=1)
    # projetos que não passam pela sede e não passam pela mesorregião da sede
    # (inclui os executados só fora de Minas Gerais)
    outra_meso = cap.apply(lambda r: r["sede_meso"] not in r["meso_exec"], axis=1) & ~na_sede
    bh = cap[cap["sede"] == "BELO HORIZONTE"]
    tot = cap["captado"].sum()
    I = {
        "projetos protocolados": len(proj),
        "indeferidos": int((st == "Indeferidos").sum()),
        "em análise": int((st == "Análise").sum()),
        "habilitados": len(hab),
        "habilitados que captaram": len(cap),
        "% que captaram": pct(len(cap), len(hab)),
        "valor aprovado (habilitados)": round(hab[COL_APROVADO].sum(), 2),
        "valor captado (habilitados)": round(hab["captado"].sum(), 2),
        "taxa de conversão (%)": pct(hab["captado"].sum(), hab[COL_APROVADO].sum()),
        "prefeituras e órgãos públicos: projetos protocolados": int((proj["tipo"] == "Prefeitura ou órgão público").sum()),
        "executores que captaram": cap["cnpj_executor"].nunique(),
        "termos de compromisso": len(termos),
        "valor dos termos": round(termos["valor"].sum(), 2),
        "CNPJs distintos": termos["cnpj"].nunique(),
        "empresas (raiz do CNPJ)": len(emp),
        "valor mediano do termo": round(termos["valor"].median(), 2),
        "valor médio do termo": round(termos["valor"].mean(), 2),
        "% das 10 maiores empresas": pct(v.head(10).sum(), v.sum()),
        "% das 20 maiores empresas": pct(v.head(20).sum(), v.sum()),
        "20% maiores empresas (número)": n20,
        "% dos 20% maiores": pct(v.head(n20).sum(), v.sum()),
        "% dos 10 maiores grupos": pct(T["tabela08_grupos"]["valor"].sum(), v.sum()),
        "municípios de MG com projetos": int(cap.explode("mun_mg")["mun_mg"].nunique()),
        "projetos em mais de um município": int((multi > 1).sum()),
        "máximo de municípios num projeto": int(multi.max()),
        "projetos com execução fora de MG": int(fora.sum()),
        "projetos só fora de MG": int(so_fora.sum()),
        "projetos com a sede entre os locais de execução": int(na_sede.sum()),
        "projetos só em outros municípios": int((~na_sede).sum()),
        "% do valor dos projetos só em outros municípios": pct(cap.loc[~na_sede, "captado"].sum(), tot),
        "desses, em outra mesorregião": int(outra_meso.sum()),
        "% do valor das entidades de BH": pct(bh["captado"].sum(), tot),
        "projetos de entidades de BH": len(bh),
        "projetos de entidades de BH executados fora de BH": int((~bh["mun_mg"].map(lambda m: "BELO HORIZONTE" in m)).sum()),
        "municípios sede de executores que captaram": cap["sede"].nunique(),
    }
    return pd.Series(I, name="valor")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projetos", required=True, help="planilha de projetos (posição 08/05/2025)")
    ap.add_argument("--termos", required=True, help="planilha de Termos de Compromisso (março/2025)")
    ap.add_argument("--saida", default="resultados", help="pasta para os resultados")
    a = ap.parse_args()

    proj, termos = ler_bases(a.projetos, a.termos)            # 1
    proj = remover_totalizacao(proj)                           # 2
    proj = padronizar_categorias(proj)                         # 3
    termos = padronizar_termos(termos)                         # 4
    proj = separar_municipios(proj)                            # 5
    hab = habilitados(proj)                                    # 6
    existe = cruzar(proj, termos)                              # 7
    emp = consolidar_apoiadores(termos)                        # 8
    hab, ibge = localizar(hab)                                 # 9
    q1 = quadro1(proj, termos, existe)                         # 10
    T = tabelas(proj, hab, termos, emp, ibge)
    ind = indicadores(proj, hab, termos, emp, T)

    out = Path(a.saida)
    out.mkdir(exist_ok=True)
    q1.to_csv(out / "quadro01_consistencia.csv", encoding="utf-8-sig")
    ind.to_csv(out / "indicadores_do_texto.csv", encoding="utf-8-sig")
    for nome, df in T.items():
        df.to_csv(out / f"{nome}.csv", encoding="utf-8-sig")
    # Lista de empresas com setor, sem dados pessoais (só razão social e raiz do CNPJ)
    emp.to_csv(out / "empresas_apoiadoras.csv", encoding="utf-8-sig")

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
    print("\nQuadro 1\n", q1.to_string())
    print("\nIndicadores\n", ind.to_string())
    for nome, df in T.items():
        if nome.startswith("tabela13") or nome.startswith("tabela12"):
            continue
        print(f"\n{nome}\n{df.to_string()}")
    print(f"\nResultados gravados em {out.resolve()}")


if __name__ == "__main__":
    main()
