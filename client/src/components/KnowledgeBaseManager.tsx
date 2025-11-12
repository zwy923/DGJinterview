import { useState, useEffect } from "react";
import { saveKnowledgeBase, getKnowledgeBase, type KnowledgeBaseResponse } from "../api/apiClient";

interface Props {
  sessionId: string;
  isTemporary?: boolean;
  onItemsChange?: (items: KnowledgeBaseResponse[]) => void;
}

export default function KnowledgeBaseManager({ sessionId, isTemporary = false, onItemsChange }: Props) {
  const [items, setItems] = useState<KnowledgeBaseResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formContent, setFormContent] = useState("");
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 加载知识库条目（非临时模式）
  useEffect(() => {
    if (isTemporary) return;
    
    const loadKnowledgeBase = async () => {
      if (!sessionId) return;
      
      setIsLoading(true);
      try {
        const kbItems = await getKnowledgeBase(sessionId);
        setItems(kbItems);
      } catch (error) {
        console.error("Failed to load knowledge base:", error);
      } finally {
        setIsLoading(false);
      }
    };

    loadKnowledgeBase();
  }, [sessionId, isTemporary]);

  // 当条目变化时通知父组件（临时模式）
  useEffect(() => {
    if (isTemporary && onItemsChange) {
      onItemsChange(items);
    }
  }, [items, isTemporary, onItemsChange]);

  // 保存知识库条目
  const handleSave = async () => {
    if (!formTitle.trim() || !formContent.trim()) {
      setMessage({ type: 'error', text: '请输入标题和内容' });
      return;
    }

    // 临时模式：只保存到本地状态
    if (isTemporary) {
      const tempItem: KnowledgeBaseResponse = {
        id: Date.now(),
        session_id: sessionId,
        title: formTitle.trim(),
        content: formContent.trim(),
        metadata: {
          created_at: new Date().toISOString(),
        },
        created_at: new Date().toISOString()
      };
      
      const newItems = [...items, tempItem];
      setItems(newItems);
      setFormTitle("");
      setFormContent("");
      setShowForm(false);
      setMessage({ type: 'success', text: '条目已添加（将在创建面试时保存）' });
      setTimeout(() => setMessage(null), 2000);
      
      // 通知父组件
      if (onItemsChange) {
        onItemsChange(newItems);
      }
      return;
    }

    setIsSaving(true);
    setMessage(null);

    try {
      const savedItem = await saveKnowledgeBase({
        session_id: sessionId,
        title: formTitle.trim(),
        content: formContent.trim(),
        metadata: {
          created_at: new Date().toISOString(),
        },
      });
      
      setItems(prev => [...prev, savedItem]);
      setFormTitle("");
      setFormContent("");
      setShowForm(false);
      setMessage({ type: 'success', text: '知识库条目添加成功！' });
      
      // 3秒后清除消息
      setTimeout(() => setMessage(null), 3000);
    } catch (error: any) {
      console.error("Failed to save knowledge base item:", error);
      setMessage({ 
        type: 'error', 
        text: error.message || '保存失败，请稍后重试' 
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      {!isTemporary && (
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: '1rem'
        }}>
          <h3 style={{ 
            fontSize: '1rem', 
            fontWeight: '600', 
            color: '#e5e7eb',
            margin: 0
          }}>
            📚 知识库管理
          </h3>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.5rem',
              border: 'none',
              background: showForm
                ? 'rgba(107, 114, 128, 0.5)'
                : 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
              color: 'white',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
              transition: 'all 0.2s ease'
            }}
          >
            {showForm ? '取消' : '+ 添加条目'}
          </button>
        </div>
      )}
      
      {isTemporary && (
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: '1rem'
        }}>
          <h4 style={{ 
            fontSize: '0.875rem', 
            fontWeight: '600', 
            color: '#e5e7eb',
            margin: 0
          }}>
            知识库条目
          </h4>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '0.4rem',
              border: 'none',
              background: showForm
                ? 'rgba(107, 114, 128, 0.5)'
                : 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
              color: 'white',
              cursor: 'pointer',
              fontSize: '0.75rem',
              fontWeight: '600',
              transition: 'all 0.2s ease'
            }}
          >
            {showForm ? '取消' : '+ 添加'}
          </button>
        </div>
      )}

      {message && (
        <div style={{
          padding: '0.75rem',
          borderRadius: '0.5rem',
          marginBottom: '1rem',
          background: message.type === 'success' 
            ? 'rgba(16, 185, 129, 0.1)' 
            : 'rgba(239, 68, 68, 0.1)',
          border: `1px solid ${message.type === 'success' 
            ? 'rgba(16, 185, 129, 0.3)' 
            : 'rgba(239, 68, 68, 0.3)'}`,
          color: message.type === 'success' ? '#10b981' : '#ef4444',
          fontSize: '0.875rem'
        }}>
          {message.text}
        </div>
      )}

      {showForm && (
        <div style={{
          padding: '1rem',
          background: 'rgba(0, 0, 0, 0.3)',
          borderRadius: '0.5rem',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          marginBottom: '1rem'
        }}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{
              display: 'block',
              fontSize: '0.875rem',
              color: '#a1a1aa',
              marginBottom: '0.5rem',
              fontWeight: '500'
            }}>
              标题 *
            </label>
            <input
              type="text"
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              placeholder="请输入标题..."
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '0.5rem',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'rgba(0, 0, 0, 0.3)',
                color: '#e5e7eb',
                fontSize: '0.875rem'
              }}
            />
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label style={{
              display: 'block',
              fontSize: '0.875rem',
              color: '#a1a1aa',
              marginBottom: '0.5rem',
              fontWeight: '500'
            }}>
              内容 *
            </label>
            <textarea
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              placeholder="请输入内容..."
              style={{
                width: '100%',
                minHeight: '120px',
                padding: '0.75rem',
                borderRadius: '0.5rem',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'rgba(0, 0, 0, 0.3)',
                color: '#e5e7eb',
                fontSize: '0.875rem',
                lineHeight: '1.6',
                fontFamily: 'inherit',
                resize: 'vertical'
              }}
            />
          </div>

          <button
            onClick={handleSave}
            disabled={isSaving || !formTitle.trim() || !formContent.trim()}
            style={{
              width: '100%',
              padding: '0.75rem',
              borderRadius: '0.5rem',
              border: 'none',
              background: isSaving || !formTitle.trim() || !formContent.trim()
                ? 'rgba(107, 114, 128, 0.5)'
                : 'linear-gradient(135deg, #10b981, #059669)',
              color: 'white',
              cursor: isSaving || !formTitle.trim() || !formContent.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
              transition: 'all 0.2s ease'
            }}
          >
            {isSaving ? '保存中...' : '保存条目'}
          </button>
        </div>
      )}

      {isLoading ? (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '0.5rem',
          color: '#a1a1aa',
          padding: '1rem'
        }}>
          <div className="loading"></div>
          正在加载知识库...
        </div>
      ) : items.length === 0 ? (
        <div style={{
          padding: '2rem',
          textAlign: 'center',
          color: '#a1a1aa',
          fontSize: '0.875rem'
        }}>
          暂无知识库条目，点击"添加条目"开始添加
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {items.map((item) => (
            <div
              key={item.id}
              style={{
                padding: '1rem',
                background: 'rgba(139, 92, 246, 0.1)',
                borderRadius: '0.5rem',
                border: '1px solid rgba(139, 92, 246, 0.3)'
              }}
            >
              <div style={{
                fontSize: '0.875rem',
                fontWeight: '600',
                color: '#e5e7eb',
                marginBottom: '0.5rem'
              }}>
                {item.title}
              </div>
              <div style={{
                fontSize: '0.8rem',
                color: '#a1a1aa',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap'
              }}>
                {item.content}
              </div>
              {item.created_at && (
                <div style={{
                  fontSize: '0.7rem',
                  color: '#71717a',
                  marginTop: '0.5rem'
                }}>
                  创建时间: {new Date(item.created_at).toLocaleString()}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

