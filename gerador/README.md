# Gerador do painel da oficina (obra 421)

Monta o `index.html` publicado no GitHub Pages a partir de três arquivos que ficam na pasta
`Indicadores Gestao Visual` do computador do Leandro:

| Arquivo | Pasta | Usado para |
|---|---|---|
| `MAQPAR dd.mm.aaaa.pdf` (o mais recente) | `Máquinas paradas/` | Tela 1 · Máquinas paradas |
| `PROJ. PREVENTIVA ... .pdf` (o mais recente) | `Preventiva/` | Telas 2 e 3 · Preventiva da semana e da próxima |
| `config.json` (senha, frota base) | `TV painel gestao a vista/` | Não vai para o GitHub |

```
pip install pdfplumber cryptography
python3 gerar.py --maqpar MAQPAR.pdf --preventiva PREVENTIVA.pdf --config config.json --saida ../index.html
```

Os dados vão criptografados dentro do `index.html` (AES-GCM, chave derivada da senha); sem a senha a página só mostra a tela de bloqueio.
O painel escolhe sozinho a semana atual e a próxima pela data do dia.
