import { useState, useEffect } from "react";
import { saveJobPosition, getJobPosition, type JobPositionResponse } from "../api/apiClient";

interface Props {
  sessionId: string;
  isTemporary?: boolean;
  onDataChange?: (data: { title: string; description?: string; requirements?: string }) => void;
}

export default function JobPositionManager({ sessionId, isTemporary = false, onDataChange }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState("");
  const [currentJob, setCurrentJob] = useState<JobPositionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 加载现有岗位信息（非临时模式）
  useEffect(() => {
    if (isTemporary) return;
    
    const loadJobPosition = async () => {
      if (!sessionId) return;
      
      setIsLoading(true);
      try {
        const job = await getJobPosition(sessionId);
        if (job) {
          setCurrentJob(job);
          setTitle(job.title);
          setDescription(job.description || "");
          setRequirements(job.requirements || "");
        }
      } catch (error) {
        console.error("Failed to load job position:", error);
      } finally {
        setIsLoading(false);
      }
    };

    loadJobPosition();
  }, [sessionId, isTemporary]);

  // 当数据变化时通知父组件（临时模式）
  useEffect(() => {
    if (isTemporary && onDataChange) {
      onDataChange({
        title,
        description,
        requirements
      });
    }
  }, [title, description, requirements, isTemporary, onDataChange]);

  // 保存岗位信息
  const handleSave = async () => {
    if (!title.trim()) {
      setMessage({ type: 'error', text: '请输入岗位名称' });
      return;
    }

    // 临时模式不保存到后端
    if (isTemporary) {
      setMessage({ type: 'success', text: '信息已更新（将在创建面试时保存）' });
      setTimeout(() => setMessage(null), 2000);
      return;
    }

    setIsSaving(true);
    setMessage(null);

    try {
      const savedJob = await saveJobPosition({
        session_id: sessionId,
        title: title.trim(),
        description: description.trim() || undefined,
        requirements: requirements.trim() || undefined,
        metadata: {
          updated_at: new Date().toISOString(),
        },
      });
      
      setCurrentJob(savedJob);
      setMessage({ type: 'success', text: '岗位信息保存成功！' });
      
      // 3秒后清除消息
      setTimeout(() => setMessage(null), 3000);
    } catch (error: any) {
      console.error("Failed to save job position:", error);
      setMessage({ 
        type: 'error', 
        text: error.message || '保存失败，请稍后重试' 
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div style={isTemporary ? {} : { marginBottom: '1.5rem' }}>
      {!isTemporary && (
        <h3 style={{ 
          fontSize: '1rem', 
          fontWeight: '600', 
          color: '#e5e7eb',
          marginBottom: '1rem'
        }}>
          💼 岗位信息管理
        </h3>
      )}
      
      {isTemporary && (
        <div style={{ 
          fontSize: '0.75rem', 
          color: '#a1a1aa',
          marginBottom: '0.75rem'
        }}>
          提示：填写岗位详细信息，这些信息将用于面试辅助
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
          正在加载岗位信息...
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

          <div style={{ marginBottom: '1rem' }}>
            <label style={{
              display: 'block',
              fontSize: '0.875rem',
              color: '#a1a1aa',
              marginBottom: '0.5rem',
              fontWeight: '500'
            }}>
              岗位名称 *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：高级前端开发工程师"
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
              岗位描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="请输入岗位描述..."
              style={{
                width: '100%',
                minHeight: '100px',
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

          <div style={{ marginBottom: '1rem' }}>
            <label style={{
              display: 'block',
              fontSize: '0.875rem',
              color: '#a1a1aa',
              marginBottom: '0.5rem',
              fontWeight: '500'
            }}>
              岗位要求
            </label>
            <textarea
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              placeholder="请输入岗位要求..."
              style={{
                width: '100%',
                minHeight: '100px',
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

          {currentJob && (
            <div style={{
              fontSize: '0.75rem',
              color: '#a1a1aa',
              marginBottom: '1rem'
            }}>
              最后更新: {currentJob.updated_at 
                ? new Date(currentJob.updated_at).toLocaleString() 
                : '未知'}
            </div>
          )}

          {!isTemporary && (
            <button
              onClick={handleSave}
              disabled={isSaving || !title.trim()}
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '0.5rem',
                border: 'none',
                background: isSaving || !title.trim()
                  ? 'rgba(107, 114, 128, 0.5)'
                  : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                color: 'white',
                cursor: isSaving || !title.trim() ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem',
                fontWeight: '600',
                transition: 'all 0.2s ease'
              }}
            >
              {isSaving ? '保存中...' : '保存岗位信息'}
            </button>
          )}
        </>
      )}
    </div>
  );
}

