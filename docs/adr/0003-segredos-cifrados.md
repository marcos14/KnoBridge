# ADR 0003 — Segredos cifrados em repouso

> Status: aceito · 2026-10-10 · plano 0002 (F4.1)

## Contexto

O workspace precisa guardar chaves de API de provedores de LLM (OpenAI, Anthropic, OpenRouter; decisão D11 da [visão](../01-visao-do-projeto.md)) para os assistentes. Depois virão tokens de conectores e de canais. A regra da seção 9 do [AGENTS.md da raiz](../../AGENTS.md) exige segredos cifrados em repouso, nunca em log e nunca em resposta de API. Faltava decidir o algoritmo, de onde vem a chave, o formato gravado e como impedir que um texto cifrado copiado para outra linha ou outro workspace seja aceito. A instância já tem um segredo raiz, `KNOBRIDGE_SECRET_KEY`, usado no HMAC do CSRF ([ADR 0002](0002-sessao-server-side.md)).

## Decisão

1. **AES-256-GCM** (cifra autenticada) pela biblioteca `cryptography` (`AESGCM`), em `backend/src/knobridge/core/crypto.py` (`SecretBox`). Nonce aleatório de 96 bits por cifragem (`os.urandom`): o mesmo valor cifrado duas vezes dá textos diferentes.
2. **Chave de dados derivada, uma por finalidade**: HKDF-SHA256 sobre `KNOBRIDGE_SECRET_KEY`, com sal fixo e um `info` próprio de cada tipo de segredo. Credenciais de provedor usam `knobridge/provider-credentials/v1`. Assim a chave do HMAC do CSRF e cada chave de dados são independentes, mesmo vindo do mesmo segredo raiz; um `info` novo (`.../v2`) gera uma chave nova.
3. **Formato gravado**: `v<versão da chave>.<base64url(nonce || texto cifrado || tag)>`, numa coluna `text`. Hoje só existe a versão `1`; o prefixo deixa a rotação futura decifrar linhas antigas com a chave anterior e cifrar as novas com a atual. Versão desconhecida, base64 inválido, tamanho curto ou tag inválida dão o mesmo `DecryptionError`.
4. **Dados associados (AAD) amarram o texto cifrado à linha**: para credenciais, `provider_credential:<workspace_id>:<id da credencial>`. O id é gerado na aplicação antes de cifrar. Copiado para outra linha ou outro workspace, o texto cifrado falha na autenticação em vez de decifrar.
5. **A chave nunca volta**: a API devolve só `key_hint` (`****` + os 4 últimos caracteres, guardados em `key_last4`); por isso a chave precisa ter ao menos 8 caracteres. A auditoria registra nome, tipo e campos alterados (`key`), nunca o valor. O texto em claro só sai por `ProviderCredentialService.reveal_key`, para chamar o provedor.
6. **Escopo**: `provider_credentials` é dado de workspace, com RLS forçada pela política padrão do [ADR 0001](0001-tenancy-e-rls.md). Owner, admin e editor gerenciam; viewer recebe 403.

## Alternativas consideradas

- **Fernet** (`cryptography.fernet`): simples, mas é AES-128-CBC + HMAC sem dados associados; não amarra o texto cifrado à linha. Descartado.
- **`pgcrypto` no Postgres**: a chave teria de ir ao banco a cada consulta (e aparecer em logs de SQL). Descartado.
- **Usar `KNOBRIDGE_SECRET_KEY` direto como chave AES**: mesma chave para HMAC e cifra, e tamanho variável. Descartado em favor do HKDF.
- **KMS ou Vault externos**: melhor separação, mas acrescenta dependência de infraestrutura a toda instalação auto-hospedada. Fica como evolução: o `SecretBox` é o único ponto a trocar.
- **Variável de ambiente própria para a chave de dados**: mais uma configuração obrigatória sem ganho real enquanto o segredo raiz é um só. Descartada por ora; a versão no formato permite introduzi-la depois.

## Consequências

- Trocar `KNOBRIDGE_SECRET_KEY` hoje invalida as sessões CSRF **e** torna as credenciais gravadas indecifráveis. Até existir rotação (chave anterior em configuração + recifragem com a versão `2`), quem troca o segredo precisa recadastrar as chaves dos provedores. O aviso está em `backend/.env.example` e no `backend/README.md`.
- Todo segredo novo (tokens de conectores e canais) usa o `SecretBox` com um `info` próprio e AAD com `workspace_id` e o id da linha.
- Assistentes (plano 0002, F4.3) referenciam credenciais com `ON DELETE RESTRICT`: credencial em uso não pode ser excluída.
- Modelo de dados em [docs/specs/modelo-de-dados.md](../specs/modelo-de-dados.md); código em `backend/src/knobridge/core/crypto.py` e `backend/src/knobridge/llm/`.
