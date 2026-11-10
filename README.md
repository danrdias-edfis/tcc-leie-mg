# LEIE/MG: rotina de tratamento dos dados

Código do Trabalho de Conclusão de Curso *Lei Estadual de Incentivo ao Esporte de Minas Gerais* (Daniel Resende Dias, Escola de Educação Física, Fisioterapia e Terapia Ocupacional da UFMG, 2026). A rotina está descrita no Apêndice D do trabalho e reproduz suas tabelas e números.

## Dados de entrada

As duas planilhas foram fornecidas pela Secretaria de Estado de Desenvolvimento Social de Minas Gerais (SEDESE):

| Base | Posição | Referência no TCC |
|---|---|---|
| Captação por projeto (`2025_05_08-Captacao-por-projeto.xlsx`) | 08/05/2025 | Minas Gerais (2025a) |
| Captação por inscrição estadual (`captacao_por_inscricao_estadual-Marc_o-2025.xlsx`) | março de 2025 | Minas Gerais (2025b) |

**As planilhas não estão neste repositório**, porque a base de projetos traz nome, e-mail e telefone dos representantes legais das entidades. A rotina descarta esses campos já na leitura e não os usa em nenhuma etapa. Quem quiser reproduzir a análise pode solicitar as bases à SEDESE.

## Como executar

Requer Python 3.10 ou superior.

```bash
pip install -r requirements.txt
python rotina_leie_mg.py --projetos caminho/projetos.xlsx --termos caminho/termos.xlsx --saida resultados
```

A rotina mostra os resultados na tela e grava, na pasta `resultados`, um arquivo CSV para cada quadro e tabela (`quadro01_...`, `tabela02_...` a `tabela13_...`, `grafico01_...`), um arquivo `indicadores_do_texto.csv` com os números citados no texto e a lista das empresas apoiadoras com o setor atribuído.

## Etapas

As etapas seguem a ordem do Apêndice D:

1. leitura das planilhas, sem os campos de contato pessoal;
2. remoção das duas linhas de totalização;
3. padronização do tipo de executor (três categorias) e da grafia da dimensão esportiva;
4. padronização do número do projeto nos Termos de Compromisso e dos CNPJs;
5. separação dos municípios de execução e correção de grafias;
6. definição dos 1.910 projetos habilitados à captação;
7. cruzamento das bases pelo número do projeto;
8. consolidação dos apoiadores por raiz do CNPJ, grupo econômico e setor;
9. município sede dos executores e mesorregiões;
10. verificações de consistência e cálculo das tabelas.

## Dados auxiliares (`dados_auxiliares/`)

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `tipos_executor.csv` | rótulos de tipo de executor e a categoria atribuída | classificação do autor |
| `correcoes_municipios.csv` | grafias de municípios corrigidas para a forma do IBGE | classificação do autor |
| `municipios_mg_ibge.csv` | os 853 municípios de Minas Gerais, com código e mesorregião | API de localidades do IBGE (IBGE, [2026]) |
| `sedes_executores.csv` | município sede das 240 entidades executoras que captaram | consulta pelo CNPJ (Minha Receita, [2026]) |
| `grupos_economicos.csv` | raízes de CNPJ reunidas nos grupos Cemig, Sada, Usiminas e Algar (Apêndice B) | classificação do autor |
| `setores.csv` | setor de atividade de cada empresa apoiadora, atribuído pela razão social | classificação do autor |
| `limite_anual.csv` | limite anual de captação, 2014 a 2024 | balanço da SEDESE (Minas Gerais, [2026a]) |

Todos os dados auxiliares se referem a pessoas jurídicas. Nenhum contém dado pessoal.

## Decisões de tratamento

- **Projetos habilitados à captação**: todos, exceto os indeferidos e os que estavam em análise na data de corte.
- **Valores com erro de digitação**: uma célula de valor captado em 2023 está gravada como texto ("R$ 25.000,00") e um Termo de Compromisso traz o valor como texto ("R$ 5.000,00"). Os dois são tratados como sem valor.
- **CNPJ dos apoiadores**: quando vem formatado, cada parte é completada com zeros (há uma filial digitada com três dígitos); quando vem como número, os zeros iniciais perdidos são recolocados. A empresa é identificada pelos oito primeiros dígitos (raiz). A Unilever, registrada com duas raízes, é contada uma vez.
- **Municípios de execução**: um projeto executado em vários municípios é contado em cada um deles. O valor captado é atribuído ao município sede do executor, que é único.
- **Bases não somadas**: a base de projetos é a referência para os totais; a base de Termos de Compromisso descreve só o perfil das empresas apoiadoras.

## Uso de inteligência artificial

A rotina foi escrita e depurada com o apoio da ferramenta Claude (Anthropic), a partir dos procedimentos definidos pelo autor, como informa a declaração de uso de IA do trabalho.

## Licença

Código disponibilizado sob a licença MIT.
