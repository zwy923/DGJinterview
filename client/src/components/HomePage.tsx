import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import CVManager from "./CVManager";
import JobPositionManager from "./JobPositionManager";
import KnowledgeBaseManager from "./KnowledgeBaseManager";
import { saveJobPosition, saveKnowledgeBase } from "../api/apiClient";

interface InterviewConfig {
  id: string;
  programmingLanguages: string[];
  position: string;
  jobRequirements: string;
  createdAt: string;
}

const PROGRAMMING_LANGUAGES = [
  "JavaScript", "TypeScript", "Python", "Java", "C++", "C#", "Go", "Rust",
  "PHP", "Ruby", "Swift", "Kotlin", "Scala", "R", "MATLAB", "其他"
];

export default function HomePage() {
  const navigate = useNavigate();
  const [showNewInterview, setShowNewInterview] = useState(false);
  const [interviewHistory, setInterviewHistory] = useState<InterviewConfig[]>([]);
  const [formData, setFormData] = useState<Partial<InterviewConfig>>({
    programmingLanguages: []
  });
  const [showCVManager, setShowCVManager] = useState(false);
  const [userId] = useState("default_user"); // 可以从用户系统获取
  const [tempKnowledgeBaseItems, setTempKnowledgeBaseItems] = useState<any[]>([]);
  const [jobPositionData, setJobPositionData] = useState<{ title: string; description?: string; requirements?: string } | null>(null);

  const handleLanguageToggle = (language: string) => {
    setFormData(prev => ({
      ...prev,
      programmingLanguages: prev.programmingLanguages?.includes(language)
        ? prev.programmingLanguages.filter(l => l !== language)
        : [...(prev.programmingLanguages || []), language]
    }));
  };

  const handleSubmit = async () => {
    if (!jobPositionData || !jobPositionData.title?.trim()) {
      alert("请填写岗位名称");
      return;
    }

    const newInterview: InterviewConfig = {
      id: Date.now().toString(),
      programmingLanguages: formData.programmingLanguages || [],
      position: jobPositionData.title,
      jobRequirements: jobPositionData.requirements || jobPositionData.description || "",
      createdAt: new Date().toISOString()
    };

    // 保存到本地存储
    const existingHistory = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
    const updatedHistory = [newInterview, ...existingHistory];
    localStorage.setItem('interviewHistory', JSON.stringify(updatedHistory));
    setInterviewHistory(updatedHistory);

    // 保存岗位信息到后端
    try {
      await saveJobPosition({
        session_id: newInterview.id,
        title: jobPositionData.title.trim(),
        description: jobPositionData.description?.trim() || undefined,
        requirements: jobPositionData.requirements?.trim() || undefined,
        metadata: {
          programmingLanguages: formData.programmingLanguages,
          createdAt: newInterview.createdAt
        }
      });
    } catch (error) {
      console.error("保存岗位信息失败:", error);
    }

    // 保存知识库条目到后端（如果有添加）
    if (tempKnowledgeBaseItems.length > 0) {
      try {
        await Promise.all(
          tempKnowledgeBaseItems.map(item =>
            saveKnowledgeBase({
              session_id: newInterview.id,
              title: item.title,
              content: item.content,
              metadata: item.metadata
            })
          )
        );
      } catch (error) {
        console.error("保存知识库条目失败:", error);
      }
    }

    // 重置临时数据
    setTempKnowledgeBaseItems([]);
    setJobPositionData(null);

    // 关闭模态框
    setShowNewInterview(false);

    // 跳转到面试页面
    navigate(`/interview/${newInterview.id}`);
  };

  const loadInterviewHistory = () => {
    const history = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
    setInterviewHistory(history);
  };

  const handleDeleteInterview = (interviewId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止事件冒泡
    if (window.confirm('确定要删除这个面试记录吗？')) {
      const existingHistory = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
      const updatedHistory = existingHistory.filter((item: InterviewConfig) => item.id !== interviewId);
      localStorage.setItem('interviewHistory', JSON.stringify(updatedHistory));
      setInterviewHistory(updatedHistory);
    }
  };

  // 组件挂载时加载历史记录
  useEffect(() => {
    loadInterviewHistory();
  }, []);

  return (
    <div className="homepage">
      <div className="homepage-header">
        <h1 className="homepage-title">
          <span className="title-icon">🎯</span>
          11
        </h1>
        <p className="homepage-subtitle">AI面试辅助</p>
      </div>

      <div className="homepage-content">
        {/* CV管理区域 */}
        <div style={{
          marginBottom: '2rem',
          padding: '1.5rem',
          background: 'rgba(0, 0, 0, 0.3)',
          borderRadius: '1rem',
          border: '1px solid rgba(255, 255, 255, 0.1)'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1rem'
          }}>
            <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#e5e7eb' }}>📄 简历管理</h2>
            <button
              onClick={() => setShowCVManager(!showCVManager)}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '0.5rem',
                border: 'none',
                background: showCVManager 
                  ? 'rgba(107, 114, 128, 0.5)' 
                  : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                color: 'white',
                cursor: 'pointer',
                fontSize: '0.875rem',
                fontWeight: '600'
              }}
            >
              {showCVManager ? '收起' : '管理简历'}
            </button>
          </div>
          {showCVManager && (
            <CVManager userId={userId} />
          )}
        </div>

        {/* 新建面试按钮 */}
        <div className="new-interview-section">
          <button 
            className="new-interview-btn"
            onClick={() => setShowNewInterview(true)}
          >
            <span className="btn-icon">➕</span>
            新建面试
          </button>
          <button 
            className="new-interview-btn audio-test-btn"
            onClick={() => navigate('/test/audio')}
          >
            <span className="btn-icon">🧪</span>
            音频识别测试
          </button>
        </div>

        {/* 面试历史 */}
        <div className="interview-history">
          <h2>面试历史</h2>
          {interviewHistory.length === 0 ? (
            <div className="empty-history">
              <p>暂无面试记录</p>
              <p>点击"新建面试"开始您的第一次面试</p>
            </div>
          ) : (
            <div className="history-list">
              {interviewHistory.map(interview => (
                <div key={interview.id} className="history-item">
                  <div className="history-info">
                    <h3>{interview.position}</h3>
                    <p className="history-date">
                      {new Date(interview.createdAt).toLocaleString()}
                    </p>
                    <div className="history-tags">
                      {interview.programmingLanguages.slice(0, 3).map(lang => (
                        <span key={lang} className="tag">{lang}</span>
                      ))}
                      {interview.programmingLanguages.length > 3 && (
                        <span className="tag">+{interview.programmingLanguages.length - 3}</span>
                      )}
                    </div>
                  </div>
                  <div className="history-actions">
                    <button 
                      className="continue-btn"
                      onClick={() => navigate(`/interview/${interview.id}`)}
                    >
                      继续面试
                    </button>
                    <button 
                      className="delete-btn"
                      onClick={(e) => handleDeleteInterview(interview.id, e)}
                      title="删除面试"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 新建面试模态框 */}
      {showNewInterview && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h2>新建面试</h2>
              <button 
                className="close-btn"
                onClick={() => {
                  setShowNewInterview(false);
                  // 重置表单数据
                  setFormData({
                    programmingLanguages: []
                  });
                  setJobPositionData(null);
                  setTempKnowledgeBaseItems([]);
                }}
              >
                ✕
              </button>
            </div>

            <div className="modal-content">
              {/* 编程语言选择 */}
              <div className="form-section">
                <label className="form-label">支持的编程语言</label>
                <div className="language-grid">
                  {PROGRAMMING_LANGUAGES.map(language => (
                    <button
                      key={language}
                      className={`language-btn ${
                        formData.programmingLanguages?.includes(language) ? 'selected' : ''
                      }`}
                      onClick={() => handleLanguageToggle(language)}
                    >
                      {language}
                    </button>
                  ))}
                </div>
              </div>

              {/* 岗位信息管理 */}
              <div className="form-section">
                <label className="form-label">岗位信息 *</label>
                <div style={{
                  padding: '1rem',
                  background: 'rgba(0, 0, 0, 0.2)',
                  borderRadius: '0.5rem',
                  border: '1px solid rgba(255, 255, 255, 0.1)'
                }}>
                  <JobPositionManager 
                    sessionId="temp" 
                    isTemporary={true}
                    onDataChange={(data) => {
                      setJobPositionData(data);
                    }}
                  />
                </div>
              </div>

              {/* 知识库管理 */}
              <div className="form-section">
                <label className="form-label">知识库管理（可选）</label>
                <div style={{
                  padding: '1rem',
                  background: 'rgba(0, 0, 0, 0.2)',
                  borderRadius: '0.5rem',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  maxHeight: '300px',
                  overflowY: 'auto'
                }}>
                  <KnowledgeBaseManager 
                    sessionId="temp"
                    isTemporary={true}
                    onItemsChange={setTempKnowledgeBaseItems}
                  />
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button 
                className="cancel-btn"
                onClick={() => {
                  setShowNewInterview(false);
                  // 重置表单数据
                  setFormData({
                    programmingLanguages: []
                  });
                  setJobPositionData(null);
                  setTempKnowledgeBaseItems([]);
                }}
              >
                取消
              </button>
              <button 
                className="submit-btn"
                onClick={handleSubmit}
              >
                开始面试
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
