export interface TokenRequestPayload {
  identity: string;
  name?: string;
  room?: string;
  metadata?: Record<string, unknown>;
}

export interface TokenResponsePayload {
  token: string;
  url?: string;
  room?: string;
  identity?: string;
}

export interface DispatchRequestPayload {
  room?: string;
  metadata?: Record<string, unknown>;
  force_new?: boolean;
}

export interface DispatchResponsePayload {
  room: string;
  dispatch_id: string;
  created: boolean;
}

const parseErrorBody = async (response: Response): Promise<string> => {
  const raw = await response.text();
  if (!raw) {
    return '';
  }

  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown };

    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
    if (typeof parsed.message === 'string' && parsed.message.trim()) {
      return parsed.message.trim();
    }
  } catch {
    // Fallback para texto simples.
  }

  return raw.trim();
};

export async function requestLivekitToken(
  endpoint: string,
  payload: TokenRequestPayload,
): Promise<TokenResponsePayload> {
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    const detail = error instanceof Error && error.message ? ` (${error.message})` : '';
    throw new Error(
      `Nao foi possivel acessar o endpoint de token (${endpoint}). Verifique se o token server esta ativo e com CORS liberado.${detail}`,
    );
  }

  if (!response.ok) {
    const detail = await parseErrorBody(response);
    throw new Error(detail || `Falha ao obter token LiveKit (${response.status}).`);
  }

  const parsed = (await response.json()) as TokenResponsePayload;
  if (!parsed.token) {
    throw new Error('Resposta de token invalida: campo `token` ausente.');
  }

  return parsed;
}

export async function requestLivekitDispatch(
  endpoint: string,
  payload: DispatchRequestPayload,
): Promise<DispatchResponsePayload> {
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    const detail = error instanceof Error && error.message ? ` (${error.message})` : '';
    throw new Error(`Nao foi possivel acionar o dispatch do agente (${endpoint}).${detail}`);
  }

  if (!response.ok) {
    const detail = await parseErrorBody(response);
    throw new Error(detail || `Falha ao criar dispatch do agente (${response.status}).`);
  }

  return (await response.json()) as DispatchResponsePayload;
}
