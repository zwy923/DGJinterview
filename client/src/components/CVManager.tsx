import { useState, useEffect } from "react";
import { saveCV, getCV, type CVResponse } from "../api/apiClient";

interface Props {
  userId: string;
}

export default function CVManager({ userId }: Props) {
  const [content, setContent] = useState("");
  const [currentCV, setCurrentCV] = useState<CVResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 加载现有 CV
  useEffect(() => {
    const loadCV = async () => {
      if (!userId) return;
      
      setIsLoading(true);
      try {
        const cv = await getCV(userId);
        if (cv) {
          setCurrentCV(cv);
          setContent(cv.content);
        }
      } catch (error) {
        console.error("Failed to load CV:", error);
      } finally {
        setIsLoading(false);
      }
    };

    loadCV();
  }, [userId]);

  // 保存 CV
  const handleSave = async () => {
    if (!content.trim()) {
      setMessage({ type: 'error', text: '请输入简历内容' });
      return;
    }

    setIsSaving(true);
    setMessage(null);

    try {
      const savedCV = await saveCV({
        user_id: userId,
        content: content.trim(),
        metadata: {
          updated_at: new Date().toISOString(),
        },
      });
      
      setCurrentCV(savedCV);
      setMessage({ type: 'success', text: '简历保存成功！' });
      
      // 3秒后清除消息
      setTimeout(() => setMessage(null), 3000);
    } catch (error: any) {
      console.error("Failed to save CV:", error);
      setMessage({ 
        type: 'error', 
        text: error.message || '保存失败，请稍后重试' 
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ 
        fontSize: '1rem', 
        fontWeight: '600', 
        color: '#e5e7eb',
        marginBottom: '1rem'
      }}>
        📄 简历管理
      </h3>

      {isLoading ? (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '0.5rem',
          color: '#a1a1aa',
          padding: '1rem'
        }}>
          <div className="loading"></div>
          正在加载简历...
        </div>
      ) : (
        <>
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

          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="请输入您的简历内容..."
            style={{
              width: '100%',
              minHeight: '200px',
              padding: '1rem',
              borderRadius: '0.5rem',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(0, 0, 0, 0.3)',
              color: '#e5e7eb',
              fontSize: '0.875rem',
              lineHeight: '1.6',
              fontFamily: 'inherit',
              resize: 'vertical',
              marginBottom: '1rem'
            }}
          />

          {currentCV && (
            <div style={{
              fontSize: '0.75rem',
              color: '#a1a1aa',
              marginBottom: '1rem'
            }}>
              最后更新: {currentCV.updated_at 
                ? new Date(currentCV.updated_at).toLocaleString() 
                : '未知'}
            </div>
          )}

          <button
            onClick={handleSave}
            disabled={isSaving || !content.trim()}
            style={{
              width: '100%',
              padding: '0.75rem',
              borderRadius: '0.5rem',
              border: 'none',
              background: isSaving || !content.trim()
                ? 'rgba(107, 114, 128, 0.5)'
                : 'linear-gradient(135deg, #10b981, #059669)',
              color: 'white',
              cursor: isSaving || !content.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
              transition: 'all 0.2s ease'
            }}
          >
            {isSaving ? '保存中...' : '保存简历'}
          </button>
        </>
      )}
    </div>
  );
}

