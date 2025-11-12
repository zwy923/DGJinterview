/**
 * 统一的后端 API 客户端
 */

const API_BASE_URL = `http://${window.location.hostname}:8000/api`;

interface ApiResponse<T> {
  success?: boolean;
  data?: T;
  message?: string;
  error?: string;
}

/**
 * 通用 API 请求函数
 */
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(errorData.error || errorData.message || `HTTP ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`API request failed: ${endpoint}`, error);
    throw error;
  }
}

// =====================================================
// 聊天历史相关 API
// =====================================================

export interface ChatMessage {
  id?: number;
  speaker: 'user' | 'interviewer' | 'system';
  content: string;
  timestamp?: string;
  metadata?: Record<string, any>;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
}

export interface ChatStatsResponse {
  total_messages: number;
  user_messages: number;
  interviewer_messages: number;
  system_messages: number;
  last_activity?: string;
}

/**
 * 获取聊天历史
 */
export async function getChatHistory(sessionId: string): Promise<ChatMessage[]> {
  const response = await request<ChatHistoryResponse>(`/chat/history/${sessionId}`);
  return response.messages || [];
}

/**
 * 获取聊天统计信息
 */
export async function getChatStats(sessionId: string): Promise<ChatStatsResponse> {
  return await request<ChatStatsResponse>(`/chat/stats/${sessionId}`);
}

/**
 * 保存聊天消息
 */
export async function saveChatMessage(
  sessionId: string,
  message: Omit<ChatMessage, 'id' | 'timestamp'>
): Promise<{ success: boolean; message: string }> {
  return await request<{ success: boolean; message: string }>('/chat/save', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      message: {
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        ...message,
      },
    }),
  });
}

// =====================================================
// CV 相关 API
// =====================================================

export interface CVRequest {
  user_id: string;
  content: string;
  metadata?: Record<string, any>;
}

export interface CVResponse {
  id: number;
  user_id: string;
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

/**
 * 保存/更新 CV
 */
export async function saveCV(data: CVRequest): Promise<CVResponse> {
  return await request<CVResponse>('/cv', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 获取 CV
 */
export async function getCV(userId: string): Promise<CVResponse | null> {
  try {
    return await request<CVResponse>(`/cv/${userId}`);
  } catch (error: any) {
    if (error.message?.includes('404') || error.message?.includes('未找到')) {
      return null;
    }
    throw error;
  }
}

// =====================================================
// 岗位信息相关 API
// =====================================================

export interface JobPositionRequest {
  session_id: string;
  title: string;
  description?: string;
  requirements?: string;
  metadata?: Record<string, any>;
}

export interface JobPositionResponse {
  id: number;
  session_id: string;
  title: string;
  description?: string;
  requirements?: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

/**
 * 保存/更新岗位信息
 */
export async function saveJobPosition(data: JobPositionRequest): Promise<JobPositionResponse> {
  return await request<JobPositionResponse>('/job-position', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 获取岗位信息
 */
export async function getJobPosition(sessionId: string): Promise<JobPositionResponse | null> {
  try {
    return await request<JobPositionResponse>(`/job-position/${sessionId}`);
  } catch (error: any) {
    if (error.message?.includes('404') || error.message?.includes('未找到')) {
      return null;
    }
    throw error;
  }
}

// =====================================================
// 知识库相关 API
// =====================================================

export interface KnowledgeBaseRequest {
  session_id?: string;
  title: string;
  content: string;
  metadata?: Record<string, any>;
}

export interface KnowledgeBaseResponse {
  id: number;
  session_id?: string;
  title: string;
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
}

export interface KnowledgeBaseListResponse {
  items: KnowledgeBaseResponse[];
}

/**
 * 保存知识库条目
 */
export async function saveKnowledgeBase(data: KnowledgeBaseRequest): Promise<KnowledgeBaseResponse> {
  return await request<KnowledgeBaseResponse>('/knowledge-base', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * 获取知识库条目列表
 */
export async function getKnowledgeBase(sessionId: string): Promise<KnowledgeBaseResponse[]> {
  try {
    const response = await request<KnowledgeBaseListResponse>(`/knowledge-base/${sessionId}`);
    return response.items || [];
  } catch (error: any) {
    if (error.message?.includes('404')) {
      return [];
    }
    throw error;
  }
}

// =====================================================
// Agent 相关 API
// =====================================================

export interface AgentSuggestRequest {
  session_id: string;
  user_id?: string;
}

export interface AgentSuggestResponse {
  suggestion: string | null;
  success: boolean;
  message?: string | null;
}

/**
 * 获取 Agent 建议
 */
export async function getAgentSuggestion(
  sessionId: string,
  userId?: string
): Promise<AgentSuggestResponse> {
  return await request<AgentSuggestResponse>('/agent/suggest', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      user_id: userId,
    }),
  });
}

// =====================================================
// GPT 相关 API
// =====================================================

export interface GPTRequest {
  prompt: string;
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
}

export interface GPTResponse {
  reply: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

/**
 * 调用 GPT API（增强版：支持CV、知识库、岗位信息、RAG）
 * 支持流式响应
 */
export async function askGPT(
  prompt: string,
  options?: {
    stream?: boolean;
    sessionId?: string;
    userId?: string;
    useRag?: boolean;
    onChunk?: (chunk: string) => void;
  }
): Promise<string> {
  const shouldStream = options?.stream !== false; // 默认启用流式
  
  if (shouldStream && options?.onChunk) {
    // 流式响应
    const url = `${API_BASE_URL}/gpt`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt,
        stream: true,
        session_id: options?.sessionId,
        user_id: options?.userId,
        use_rag: options?.useRag !== false,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(errorData.error || errorData.message || `HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let fullContent = '';

    if (!reader) {
      throw new Error('无法读取响应流');
    }

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                fullContent += data.content;
                options.onChunk!(data.content);
              }
              if (data.done || data.error) {
                return fullContent;
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return fullContent;
  } else {
    // 非流式响应
    const response = await request<GPTResponse>('/gpt', {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        stream: false,
        session_id: options?.sessionId,
        user_id: options?.userId,
        use_rag: options?.useRag !== false,
      }),
    });
    return response.reply || '';
  }
}

// =====================================================
// 面试分析相关 API
// =====================================================

export interface InterviewAnalysisRequest {
  type: string;
  session_id: string;
  data?: Record<string, any>;
}

export interface InterviewAnalysisResponse {
  analysis: Record<string, any>;
  summary: string;
  recommendations: string[];
  score?: number;
}

/**
 * 分析面试表现
 */
export async function analyzeInterview(sessionId: string): Promise<InterviewAnalysisResponse> {
  return await request<InterviewAnalysisResponse>('/gpt/analyze', {
    method: 'POST',
    body: JSON.stringify({
      type: 'interview_analysis',
      session_id: sessionId,
      data: {},
    }),
  });
}

