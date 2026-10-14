# Embutir o widget: o chat do produto no seu site ou sistema

> Rascunho v0.1 · 2026-10-14 · Em uso (plano 0010)

Passo a passo para levar um produto do KnoBridge a um site público ou a um sistema logado com o widget embutível: um elemento `<knobridge-chat>` carregado por uma linha de `<script>` da sua instância. O visitante conversa com streaming e citações, avalia as respostas e abre chamado; a conversa volta ao recarregar a página. O widget responde **sempre no nível Usuário final**: nunca código, consultas SQL nem documentos internos, mesmo com a pessoa identificada.

Contrato completo (rotas públicas, atributos, eventos, aparência, limites e acessibilidade) em [widget.md](../specs/widget.md); decisão de arquitetura no [ADR 0009](../adr/0009-canais-mcp-e-widget.md); o nível em [Canal público](../specs/produtos-e-niveis.md#canal-público).

## Pré-requisitos

- A stack rodando ([subir-ambiente.md](subir-ambiente.md)) e um produto **ativo** que responda com fontes no nível **Usuário final** no chat do painel ([produtos-e-niveis.md](produtos-e-niveis.md), [indexar-uma-fonte.md](indexar-uma-fonte.md)). O nível Usuário final precisa de credencial e modelo em **Configurações** > **Níveis de resposta**.
- Papel **owner** ou **admin** no workspace: a tela **Widgets** não aparece para editor nem leitor (o widget expõe o produto ao público e gasta o modelo do workspace).
- Para oferecer "Abrir chamado": o webhook de chamados configurado no produto ([receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat)).
- O site precisa alcançar a instância pelo navegador do visitante. Em produção, a instância com HTTPS (ex.: `https://kb.empresa.com`); um site HTTPS não carrega script de uma instância HTTP.

## Passos

### 1. Criar o widget

1. No workspace, vá em **Widgets** > **Novo widget**.
2. **Produto**: o produto que o widget atende. Ele **não muda** depois de criado; para outro produto, crie outro widget. Um produto pode ter vários widgets (o site público e o sistema logado, cada um com os seus domínios e limites).
3. **Nome**: só aparece no painel (ex.: `Site público`). É único no workspace.
4. **Domínios permitidos** (**Origens, uma por linha**): as origens das páginas onde o chat vai rodar, com esquema, domínio e porta, sem caminho nem barra final:

   ```text
   https://www.cliente.com.br
   https://*.cliente.com.br
   http://intranet.cliente.local:8080
   ```

   O curinga `*` só vale no primeiro rótulo e casa qualquer subdomínio (não o domínio raiz). A origem da própria instância é sempre permitida, para a prévia. Até 50 origens.
5. **Aparência**: **Modo** (**Balão**, um botão no canto que abre o chat sobre a página, ou **Embutido**, o chat no lugar do elemento), **Posição do balão**, **Tema** (automático, claro ou escuro), **Cor principal** (o painel avisa quando o contraste fica abaixo de 3:1), **Título** (vazio usa o nome do produto), **Saudação** e **Texto do campo de pergunta**.
6. **Recursos e limites**: **Avaliação das respostas (👍/👎)**, **Oferecer "Abrir chamado"** (só aparece no site se o produto tem o webhook), **Perguntas por visitante (IP) por hora** (padrão 30) e **Perguntas do widget por dia** (padrão 1000, somando todos os visitantes).
7. Clique em **Criar widget**. A tela do widget abre com a mensagem "Widget … criado", o painel **Instalar no site** (a chave pública `kbp_…` e o trecho para copiar), o formulário e a **Prévia ao vivo**.

A prévia é o widget de verdade, servido pela instância, no modo embutido e com a aparência ainda não salva. **Ela conversa de verdade**: as perguntas ficam gravadas como conversas do widget, gastam o modelo do nível Usuário final e contam nos limites e em **Uso e custos**.

### 2. Instalar no site

Cole o trecho de **Instalar no site** antes do fim do `<body>` das páginas onde o chat deve aparecer, num dos domínios permitidos:

```html
<script src="https://kb.empresa.com/widget/v1/knobridge-chat.js" defer></script>
<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o"></knobridge-chat>
```

No modo embutido, ponha o elemento onde o chat deve ficar e dê a altura (mínimo de 360 px):

```html
<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o" mode="inline" style="height: 600px"></knobridge-chat>
```

- A chave pública **não é segredo**: vai no HTML. Quem a copia para outro domínio é recusado pela checagem de origem e barrado pelos limites.
- O script é um arquivo só, sem dependências, CSS nem fontes externas, e chama a API na mesma origem de onde foi carregado. Com a API noutro host, use o atributo `api-base`.
- Site com CSP: libere a origem da instância em `script-src` e `connect-src`. O widget não usa estilos nem scripts inline no documento do site (os estilos ficam no Shadow DOM).
- Num SPA (React, Vue, Angular), carregue o script uma vez no `index.html` e use o elemento nos componentes; carregar duas vezes não quebra.

### 3. Conferir num site de teste local

Para ver o widget fora do painel antes de publicar, sirva uma página de outra origem na sua máquina:

1. Inclua `http://localhost:8000` nos **Domínios permitidos** do widget e salve.
2. Numa pasta vazia, crie `index.html` com o trecho de **Instalar no site** (o `src` aponta para `http://localhost:5173` no compose):

   ```html
   <!doctype html>
   <html lang="pt-BR">
     <head><meta charset="utf-8" /><title>Loja Exemplo</title></head>
     <body>
       <h1>Loja Exemplo</h1>
       <script src="http://localhost:5173/widget/v1/knobridge-chat.js" defer></script>
       <knobridge-chat widget-key="kbp_..."></knobridge-chat>
     </body>
   </html>
   ```

3. Sirva a pasta com `python -m http.server 8000` (ou `npx serve -l 8000`) e abra <http://localhost:8000>.
4. Clique no balão, pergunte algo do produto e confira: a resposta chega aos poucos, com os marcadores `[1]` e a lista **Fontes**; 👍/👎 e **Abrir chamado** aparecem ao fim da resposta. Recarregue a página e abra o balão: a conversa continua lá.
5. Em **Conversas**, a conversa aparece como "Widget · <nome>" e "Visitante anônimo"; o filtro **Canal** tem a opção **Widget**.

O E2E da stack faz o mesmo teste ([widget.spec.ts](../../frontend/e2e/stack/widget.spec.ts)), com uma página servida noutra porta.

### 4. Aparência pelo site

Os atributos do elemento sobrepõem a configuração do painel: `mode`, `position`, `theme`, `primary-color`, `title`, `greeting` e `placeholder`. Variáveis CSS no elemento vencem os dois:

```css
knobridge-chat {
  --knobridge-primary: #0f766e;
  --knobridge-radius: 8px;
  --knobridge-font-family: "Inter", sans-serif;
  --knobridge-z-index: 1000;
}
```

As variáveis, as partes estilizáveis por `::part()` (`launcher`, `panel`, `header`, `messages`, `composer`…), os métodos (`open()`, `close()`, `toggle()`, `newConversation()`, `setIdentity()`) e os eventos (`knobridge-ready`, `knobridge-answer`, `knobridge-ticket-requested`, `knobridge-error`…) estão em [widget.md](../specs/widget.md#atributos). Por exemplo, um botão do seu menu que abre o chat:

```html
<button type="button" onclick="document.querySelector('knobridge-chat').open()">Ajuda</button>
```

### 5. Identidade assinada (opcional)

Num sistema logado, o seu **servidor** pode dizer ao KnoBridge quem está conversando: a conversa e o chamado chegam com nome, e-mail e o id da pessoa no seu sistema, e o formulário de chamado não pede o e-mail de novo. A identidade **só identifica**: o widget continua no nível Usuário final.

1. Na tela do widget, em **Identidade assinada (opcional)**, clique em **Gerar segredo**. O segredo `kbs_…` aparece **uma única vez**: copie-o para a variável `KNOBRIDGE_WIDGET_SIGNING_SECRET` do **servidor** do seu sistema (nunca no navegador, nunca no repositório). **Substituir segredo** invalida na hora as identidades assinadas com o anterior; **Remover segredo** volta todos os visitantes a anônimos.
2. A cada página, o servidor gera a identidade `v1.<payload>.<assinatura>`: o JSON `{sub, name, email, iat, exp}` em base64url sem `=` e o HMAC-SHA256 hexadecimal de `"v1." + payload` com o segredo. `sub` (o id da pessoa), `iat` e `exp` são obrigatórios; a validade é de até 24 horas.

   Python (Flask):

   ```python
   import base64, hashlib, hmac, json, os, time

   from flask import Flask, render_template
   from flask_login import current_user, login_required

   def knobridge_identity(sub: str, name: str | None, email: str | None, ttl: int = 3600) -> str:
       now = int(time.time())
       claims = {"sub": sub, "name": name, "email": email, "iat": now, "exp": now + ttl}
       claims = {k: v for k, v in claims.items() if v is not None}
       raw = json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode()
       payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
       key = os.environ["KNOBRIDGE_WIDGET_SIGNING_SECRET"].encode()  # kbs_…
       signature = hmac.new(key, f"v1.{payload}".encode(), hashlib.sha256).hexdigest()
       return f"v1.{payload}.{signature}"

   app = Flask(__name__)

   @app.get("/painel")
   @login_required
   def painel():
       identity = knobridge_identity(str(current_user.id), current_user.name, current_user.email)
       return render_template("painel.html", knobridge_identity=identity)
   ```

   Node (Express):

   ```js
   import { createHmac } from "node:crypto";

   export function knobridgeIdentity({ sub, name, email }, ttl = 3600) {
     const iat = Math.floor(Date.now() / 1000);
     const payload = Buffer.from(JSON.stringify({ sub, name, email, iat, exp: iat + ttl })).toString("base64url");
     const signature = createHmac("sha256", process.env.KNOBRIDGE_WIDGET_SIGNING_SECRET).update(`v1.${payload}`).digest("hex");
     return `v1.${payload}.${signature}`;
   }

   app.get("/painel", requireLogin, (req, res) => {
     const { id, name, email } = req.user;
     res.render("painel", { knobridgeIdentity: knobridgeIdentity({ sub: String(id), name, email }) });
   });
   ```

3. No template da página, ponha a identidade no atributo `identity` (o template escapa o valor, que só tem letras, números, `.`, `-` e `_`):

   ```html
   <knobridge-chat widget-key="kbp_..." identity="{{ knobridge_identity }}"></knobridge-chat>
   ```

   Num SPA, busque a identidade numa rota do seu servidor e chame `document.querySelector("knobridge-chat").setIdentity(identidade)`; no logout, `setIdentity(null)` e `newConversation()`.

O KnoBridge verifica a identidade ao criar a conversa (assinatura, formato, validade, com 60 s de tolerância de relógio) e grava nome, e-mail e `sub` nela. Identidade inválida é recusada (401 `widget_identity_invalid`): na primeira pergunta, o visitante vê "Não consegui responder agora. Tente de novo." e o elemento emite `knobridge-error` com esse código. Se a pessoa logada mudar (outro `sub`), o widget abre outra conversa: ninguém vê a conversa de outra pessoa no mesmo navegador. Os valores de teste da spec ([Exemplo reproduzível](../specs/widget.md#exemplo-reproduzível)) servem para conferir a sua implementação.

### 6. Acompanhar

- **Conversas**: "Widget · <nome do widget>" no lugar do usuário e, abaixo, o visitante ("Visitante anônimo" ou "Visitante: Nome (e-mail)" com identidade assinada); filtros por **Canal** (Widget) e por **Widget**; as avaliações e os pedidos de chamado de cada resposta.
- **Uso e custos**: agrupado por **Canal**, a linha **Widget**; agrupado por **Widget**, uma linha por widget. O custo de cada resposta é gravado, mas nunca vai ao visitante.
- **Chamados**: o sistema de chamados recebe `channel: "widget"` e o solicitante: com identidade assinada, nome e e-mail dela (`verified: true`, `external_id` = `sub`); sem ela, o e-mail e o nome digitados no formulário (`verified: false`).

## Limites

| Limite | Padrão | Onde muda |
|---|---|---|
| Perguntas por visitante (IP) por hora | 30 | Formulário do widget |
| Perguntas do widget por dia (todos os visitantes) | 1000 | Formulário do widget |
| Requisições por minuto, por widget e IP | 120 | `KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE` |
| Conversas novas por hora, por widget e IP | 20 | `KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR` |
| Pedidos de chamado por hora, por widget e IP | 5 | `KNOBRIDGE_WIDGET_TICKETS_PER_HOUR` |
| Tolerância de relógio da identidade | 60 s | `KNOBRIDGE_WIDGET_IDENTITY_CLOCK_SKEW` |
| Pergunta | 8000 caracteres | Fixo |

As variáveis de ambiente valem para todos os widgets da instância (no compose, no `.env` da raiz; recrie a `api` depois). Estourado um limite, a API responde 429 com `Retry-After`, e o widget mostra "Muitas mensagens em pouco tempo. Tente de novo em N minutos." Atrás de outro proxy além do nginx do painel, configure `KNOBRIDGE_FORWARDED_ALLOW_IPS` com ele, senão todos os visitantes contam como o mesmo IP.

## Privacidade

- **No navegador do visitante**: só o ponteiro da conversa (id, token da conversa, `sub` da identidade e data), no `localStorage` do próprio site, na chave `knobridge:v1:<chave pública>`. Nenhum cookie, nenhuma métrica, nenhuma requisição além da instância. As mensagens não ficam no navegador: voltam da instância ao recarregar. Com `storage="session"`, o ponteiro some ao fechar a aba; com `storage="none"`, ao recarregar.
- **Na instância**: perguntas e respostas ficam gravadas como as dos outros canais, visíveis a owner e admin em **Conversas**. Nome e e-mail só existem com identidade assinada ou quando o visitante os digita para abrir chamado. O IP **não é gravado**: entra só num HMAC do contador de limite, apagado até 24 horas depois.
- Informe na política de privacidade do seu site que o chat é atendido pelo KnoBridge da empresa e o que é enviado.

## Como desfazer

- Tirar o chat do site: remova o trecho das páginas.
- Pausar sem perder o histórico: na lista de **Widgets**, **Desativar**. O site mostra "Chat indisponível" (embutido) ou esconde o balão, e as conversas ficam.
- **Excluir** o widget apaga as conversas dele (com avaliações e pedidos de chamado), e a chave pública deixa de funcionar na hora. Para guardar o histórico, desative.

## Problemas comuns

- **O balão não aparece** (ou "Chat indisponível no momento." no modo embutido): abra as ferramentas do navegador e veja a chamada a `/v1/widget/<chave>/config`.
  - **403 `widget_origin_not_allowed`** (o console mostra um erro de CORS): a origem da página não está nos **Domínios permitidos**. Confira esquema, porta e subdomínio (`https://www.cliente.com.br` não casa `https://cliente.com.br`); use `https://*.cliente.com.br` para os subdomínios.
  - **404 `widget_unavailable`**: o widget ou o produto está desativado, ou o workspace foi suspenso.
  - **404 `not_found`**: a chave pública está errada (ou o widget foi excluído).
  - **409 `level_not_configured`** ao perguntar: o nível Usuário final não tem credencial e modelo em **Configurações**.
- **O script não carrega**: confira `curl -sI <instância>/widget/v1/knobridge-chat.js` (200, `text/javascript`). Num site HTTPS, a instância também precisa de HTTPS. Com CSP, libere a instância em `script-src` e `connect-src`.
- **Responde sempre "sem fonte"**: o widget só usa as fontes de nível Usuário final. Pergunte o mesmo no chat do painel no nível Usuário final e veja o nível mínimo das fontes ([produtos-e-niveis.md](produtos-e-niveis.md)).
- **"Abrir chamado" não aparece**: o produto não tem o webhook de chamados configurado, ou **Oferecer "Abrir chamado"** está desmarcado no widget. O pedido fica "Chamado solicitado." até o seu sistema responder; o widget consulta a cada 10 s, por um minuto.
- **401 `widget_identity_invalid`**: `details.reason` diz o motivo. `not_configured` (o widget não tem segredo), `signature` (segredo errado ou trocado, ou o payload mudou), `malformed`, `claims` (falta `sub`, `iat` ou `exp`), `lifetime_too_long` (mais de 24 h), `not_yet_valid` ou `expired` (relógio do servidor fora de hora, ou a página ficou aberta além do `exp`: gere a identidade a cada carregamento e use um `ttl` maior que a sessão típica).
- **429 `rate_limited`**: um limite da tabela acima estourou. Se muitos visitantes de uma mesma rede compartilham o IP (empresa atrás de NAT), suba **Perguntas por visitante (IP) por hora**.
- **A conversa não volta ao recarregar**: o navegador bloqueia o armazenamento do site (modo privado, política de cookies), o elemento usa `storage="none"`, ou a identidade mudou de pessoa.
