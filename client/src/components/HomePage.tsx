import { useState } from "react";
import { useNavigate } from "react-router-dom";

interface InterviewConfig {
  id: string;
  programmingLanguages: string[];
  uploadResume: boolean;
  useKnowledgeBase: boolean;
  position: string;
  jobRequirements: string;
  createdAt: string;
}

const PROGRAMMING_LANGUAGES = [
  "JavaScript", "TypeScript", "Python", "Java", "C++", "C#", "Go", "Rust",
  "PHP", "Ruby", "Swift", "Kotlin", "Scala", "R", "MATLAB", "其他"
];

const POSITIONS = [
  "前端开发工程师", "后端开发工程师", "全栈开发工程师", "移动端开发工程师",
  "数据工程师", "算法工程师", "DevOps工程师", "测试工程师", "产品经理",
  "UI/UX设计师", "其他"
];

export default function HomePage() {
  const navigate = useNavigate();
  const [showNewInterview, setShowNewInterview] = useState(false);
  const [interviewHistory, setInterviewHistory] = useState<InterviewConfig[]>([]);
  const [formData, setFormData] = useState<Partial<InterviewConfig>>({
    programmingLanguages: [],
    uploadResume: false,
    useKnowledgeBase: false,
    position: "",
    jobRequirements: ""
  });

  const handleLanguageToggle = (language: string) => {
    setFormData(prev => ({
      ...prev,
      programmingLanguages: prev.programmingLanguages?.includes(language)
        ? prev.programmingLanguages.filter(l => l !== language)
        : [...(prev.programmingLanguages || []), language]
    }));
  };

  const handleSubmit = () => {
    if (!formData.position || !formData.jobRequirements) {
      alert("请填写职位和工作要求");
      return;
    }

    const newInterview: InterviewConfig = {
      id: Date.now().toString(),
      programmingLanguages: formData.programmingLanguages || [],
      uploadResume: formData.uploadResume || false,
      useKnowledgeBase: formData.useKnowledgeBase || false,
      position: formData.position,
      jobRequirements: formData.jobRequirements,
      createdAt: new Date().toISOString()
    };

    // 保存到本地存储
    const existingHistory = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
    const updatedHistory = [newInterview, ...existingHistory];
    localStorage.setItem('interviewHistory', JSON.stringify(updatedHistory));
    setInterviewHistory(updatedHistory);

    // 跳转到面试页面
    navigate(`/interview/${newInterview.id}`);
  };

  const loadInterviewHistory = () => {
    const history = JSON.parse(localStorage.getItem('interviewHistory') || '[]');
    setInterviewHistory(history);
  };

  // 组件挂载时加载历史记录
  useState(() => {
    loadInterviewHistory();
  });

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
            className="new-interview-btn"
            onClick={() => navigate('/test/audio')}
            style={{ marginLeft: '1rem', background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}
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
                onClick={() => setShowNewInterview(false)}
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

              {/* 选项 */}
              <div className="form-section">
                <label className="form-label">选项</label>
                <div className="checkbox-group">
                  <label className="checkbox-item">
                    <input
                      type="checkbox"
                      checked={formData.uploadResume}
                      onChange={(e) => setFormData(prev => ({ ...prev, uploadResume: e.target.checked }))}
                    />
                    <span>上传简历</span>
                  </label>
                  <label className="checkbox-item">
                    <input
                      type="checkbox"
                      checked={formData.useKnowledgeBase}
                      onChange={(e) => setFormData(prev => ({ ...prev, useKnowledgeBase: e.target.checked }))}
                    />
                    <span>使用知识库</span>
                  </label>
                </div>
              </div>

              {/* 职位选择 */}
              <div className="form-section">
                <label className="form-label">面试职位</label>
                <select
                  value={formData.position}
                  onChange={(e) => setFormData(prev => ({ ...prev, position: e.target.value }))}
                  className="form-select"
                >
                  <option value="">请选择职位</option>
                  {POSITIONS.map(position => (
                    <option key={position} value={position}>{position}</option>
                  ))}
                </select>
              </div>

              {/* 工作要求 */}
              <div className="form-section">
                <label className="form-label">工作要求</label>
                <textarea
                  value={formData.jobRequirements}
                  onChange={(e) => setFormData(prev => ({ ...prev, jobRequirements: e.target.value }))}
                  placeholder="请详细描述工作要求和技能要求..."
                  className="form-textarea"
                  rows={4}
                />
              </div>
            </div>

            <div className="modal-footer">
              <button 
                className="cancel-btn"
                onClick={() => setShowNewInterview(false)}
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
