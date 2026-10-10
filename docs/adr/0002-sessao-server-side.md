# ADR 0002 — Sessão server-side, tokens de uso único e CSRF

> Status: aceito · 2026-10-10 · plano 0002 (F1.2)

## Contexto

O painel admin autentica por e-mail e senha (decisão D12 da [visão](../01-visao-do-projeto.md)). Faltava decidir como guardar a senha, como manter o usuário logado entre requisições, como emitir os tokens enviados por e-mail (redefinição de senha, verificação de e-mail, convite) e como proteger o painel contra CSRF. O [ADR 0001](0001-tenancy-e-rls.md) já define que usuários são identidades da instância e que o modo de sistema (`system_session`) é o caminho para tarefas sem workspace, como o login.

## Decisão

1. **Senha com argon2id** (`argon2-cffi`), parâmetros do perfil de baixa memória da RFC 9106 (t=3, m=64 MiB, p=4). O hash PHC carrega os parâmetros; no login, `verify_and_update` devolve um hash novo quando os parâmetros mudaram (rehash transparente).
2. **Política de senha mínima**: de 12 a 1024 caracteres, sem regras de composição (seguindo NIST SP 800-63B). O teto evita usar o hash para gastar CPU.
3. **Sessão server-side**: tabela `sessions` com o hash do token, o usuário, `created_at`, `last_seen_at`, `expires_at`, `revoked_at`, o prefixo de rede do IP (IPv4 /24, IPv6 /48) e o user-agent truncado em 200 caracteres (resumos, por LGPD). O navegador recebe só o token opaco num cookie `httpOnly` (`session_cookie_name`, `Secure` conforme `cookie_secure`, `SameSite=Lax`).
4. **Expiração deslizante**: cada validação bem-sucedida empurra `expires_at` para `agora + session_ttl` (padrão 7 dias). Sessão parada por mais de `session_ttl` morre; revogação individual (logout) e de todas as sessões do usuário (troca ou redefinição de senha, "sair de todos os dispositivos"), com opção de manter a atual.
5. **Tokens opacos**: 32 bytes aleatórios (`secrets.token_urlsafe`). No banco vai só o SHA-256 em hex; um hash rápido basta porque a entrada tem 256 bits de entropia. Tokens de e-mail ficam em `user_tokens` com finalidade, expiração e uso único; o consumo é um único `UPDATE ... WHERE used_at IS NULL AND expires_at > agora RETURNING`, o que impede uso duplo concorrente. Token inválido, expirado, usado ou de outra finalidade gera o mesmo erro (`invalid_token`), sem revelar o motivo. `user_id` é opcional só para convites, cujo destinatário pode ainda não ter conta (`CHECK`).
6. **CSRF por double-submit assinado**: cookie legível (não `httpOnly`) `knobridge_csrf` com `<nonce>.<HMAC-SHA256(secret_key, nonce)>`; o frontend repete o valor no header `X-CSRF-Token`. A dependência `require_csrf` recusa (403 `csrf_failed`) métodos não seguros sem cookie, sem header, com valores diferentes ou com assinatura inválida; `GET`, `HEAD`, `OPTIONS` e `TRACE` passam. A assinatura barra cookie plantado por subdomínio irmão sem a chave.
7. **Relógio injetável**: toda lógica de expiração recebe um `Clock` (`knobridge.core.clock`); produção usa `SystemClock`, testes usam `FrozenClock`.
8. **Escopo de RLS das tabelas de autenticação**: `sessions` e `user_tokens` são dados da instância (sem `workspace_id`), mas recebem RLS forçada como defesa em profundidade, com a política `user_id = app.user_id OR app.system = 'on'`. Consequência para quem chama os serviços:
   - criar sessão no login, validar sessão por token e emitir ou consumir token de e-mail acontecem antes de se saber quem é o usuário: rodam em `system_session`, conforme o item 7 do ADR 0001;
   - listar ou revogar as próprias sessões roda em `scoped_session(user_id=...)`; a RLS impede tocar sessões de outro usuário.
9. **Configuração**: `secret_key` (mínimo 32 caracteres; a API recusa subir em produção com o valor padrão de desenvolvimento), `session_ttl` (duração ISO 8601), `session_cookie_name` e `cookie_secure`, todas em `core/settings.py`.

## Alternativas consideradas

- **JWT sem estado no cookie ou no header**: dispensa a tabela, mas não permite revogar uma sessão nem "sair de todos os dispositivos" sem lista de bloqueio, que reintroduz o estado. Descartada.
- **bcrypt ou scrypt**: bcrypt trunca em 72 bytes e não é resistente a memória; argon2id é a recomendação atual da OWASP. Descartadas.
- **Guardar o token de sessão em claro**: um vazamento da tabela viraria sequestro de todas as sessões. Descartada.
- **Hash lento (argon2) para os tokens**: custo sem ganho, porque não há espaço de busca para força bruta. Descartado.
- **CSRF por token sincronizado guardado na sessão**: exige ler a sessão para validar e acopla CSRF à sessão; o double-submit assinado é sem estado. Descartado.
- **Só `SameSite=Lax` sem token CSRF**: não cobre navegadores antigos nem requisições do mesmo site a partir de subdomínios. Descartado como proteção única; o cookie de sessão continua `Lax`.
- **Sem RLS em `sessions` e `user_tokens`** (como `users`): mais simples, mas um erro de filtro deixaria um usuário revogar ou listar sessões de outro. Descartado.
- **Expiração absoluta além da deslizante**: fica como evolução possível (um `max_age` total por sessão), sem mudar o esquema além de uma coluna.

## Consequências

- Toda rota autenticada valida o cookie de sessão a cada requisição (uma consulta por hash indexado e uma escrita para deslizar a expiração).
- Rotas que usam o cookie de sessão e mudam estado incluem `Depends(require_csrf)`; o login entrega o cookie de sessão (`set_session_cookie`) e o cookie CSRF (`set_csrf_cookie`).
- `create_app` guarda as `Settings` em `app.state.settings`, de onde as dependências leem a configuração.
- Troca ou redefinição de senha deve chamar `revoke_all` para derrubar sessões abertas.
- Modelo de dados em [docs/specs/modelo-de-dados.md](../specs/modelo-de-dados.md); código em `backend/src/knobridge/security/`.
