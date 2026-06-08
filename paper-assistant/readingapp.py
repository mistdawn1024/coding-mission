from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import arxiv
from datetime import datetime, timedelta
import pytz
import os
import requests
import re
from collections import Counter
import sys

# 强制调试输出
def debug_print(msg):
    print(msg)
    sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# =====================================================
# DeepSeek API 配置
# =====================================================
DEEPSEEK_API_KEY = 'sk-bbfc0f995aba4308a551e97e99dd9c8f'
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 存储论文数据
papers_db = {}
user_following = {}

class ImprovedPaperAssistant:
    def __init__(self):
        self.arxiv_client = arxiv.Client(page_size=50, delay_seconds=1)
    
    def search_papers(self, query, max_results=20, sort_by='relevance'):
        """搜索论文"""
        try:
            sort_criterion = arxiv.SortCriterion.Relevance if sort_by == 'relevance' else arxiv.SortCriterion.SubmittedDate
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=sort_criterion
            )
            
            papers = []
            now_aware = datetime.now(pytz.UTC)
            
            for result in self.arxiv_client.results(search):
                pub_date = result.published
                if pub_date.tzinfo is None:
                    pub_date = pytz.UTC.localize(pub_date)
                
                paper = {
                    'id': result.entry_id,
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'doi': result.doi,
                    'is_new': (now_aware - pub_date).days <= 7
                }
                papers.append(paper)
            return papers
        except Exception as e:
            print(f"搜索错误: {e}")
            return []
    
    def get_latest_papers_by_field(self, field='cs.AI', days=7, max_results=15):
        """根据领域获取最新论文"""
        try:
            now_aware = datetime.now(pytz.UTC)
            date_threshold = (now_aware - timedelta(days=days)).strftime('%Y%m%d')
            query = f"cat:{field} AND submittedDate:[{date_threshold} TO {now_aware.strftime('%Y%m%d')}]"
            papers = self.search_papers(query, max_results=max_results, sort_by='date')
            for paper in papers:
                paper['is_new'] = True
            return papers
        except Exception as e:
            print(f"获取最新论文错误: {e}")
            return []
    
    def get_papers_by_subscription(self, user_id='default', max_results=15):
        """根据用户订阅获取论文"""
        fields = user_following.get(user_id, ['cs.AI'])
        all_papers = []
        for field in fields[:3]:
            papers = self.get_latest_papers_by_field(field, days=7, max_results=5)
            all_papers.extend(papers)
        
        seen_titles = set()
        unique_papers = []
        for paper in all_papers:
            if paper['title'] not in seen_titles:
                seen_titles.add(paper['title'])
                unique_papers.append(paper)
        
        return unique_papers[:max_results]
    
    def extract_innovation(self, summary, title):
        """从摘要中提取创新点"""
        innovation_keywords = ['propose', 'introduce', 'novel', 'first', 'state-of-the-art', 
                               '创新', '提出', '首次', '新方法', '新框架', 'improve', 'enhance']
        
        sentences = summary.replace('\n', ' ').split('.')
        innovation_sentences = []
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            for keyword in innovation_keywords:
                if keyword in sentence_lower:
                    innovation_sentences.append(sentence.strip())
                    break
            if len(innovation_sentences) >= 3:
                break
        
        if innovation_sentences:
            return innovation_sentences
        else:
            return [s.strip() for s in sentences[:2] if len(s.strip()) > 20]
    
    def generate_literature_review(self, papers, topic):
        """基于多篇论文生成文献综述"""
        if not papers or len(papers) == 0:
            return "没有找到相关论文，无法生成文献综述。请先搜索一些论文。"
        
        review = f"# 📚 《{topic}》文献综述\n\n"
        review += f"## 📊 概述\n"
        review += f"本综述基于 {len(papers[:10])} 篇相关论文，总结了该领域的研究现状和发展趋势。\n\n"
        
        papers_by_year = {}
        for paper in papers[:10]:
            year = paper['published'][:4]
            if year not in papers_by_year:
                papers_by_year[year] = []
            papers_by_year[year].append(paper)
        
        review += f"## 📅 研究时间分布\n"
        for year in sorted(papers_by_year.keys(), reverse=True):
            review += f"- {year}年：{len(papers_by_year[year])} 篇论文\n"
        
        review += f"\n## 🔬 核心研究内容\n"
        for i, paper in enumerate(papers[:5], 1):
            review += f"\n### {i}. {paper['title']}\n"
            review += f"**作者**：{', '.join(paper['authors'][:3])}\n"
            review += f"**发表时间**：{paper['published']}\n"
            review += f"**摘要**：{paper['summary'][:200]}...\n"
            
            innovations = self.extract_innovation(paper['summary'], paper['title'])
            if innovations:
                review += f"**创新点**：{innovations[0][:150]}\n"
        
        review += f"\n## 📈 研究趋势分析\n"
        all_keywords = []
        for paper in papers[:10]:
            keywords = self.extract_keywords(paper['summary'])
            all_keywords.extend(keywords)
        
        common_keywords = Counter(all_keywords).most_common(5)
        if common_keywords:
            review += f"**高频关键词**：{', '.join([kw for kw, _ in common_keywords])}\n\n"
        
        review += f"## 💡 总结与展望\n"
        review += f"该领域研究活跃，主要集中在上述方向。未来可能的发展趋势包括：\n"
        review += f"1. 更高效的算法设计\n"
        review += f"2. 跨模态融合\n"
        review += f"3. 实际应用场景的落地\n"
        
        return review
    
    def extract_keywords(self, text):
        """提取关键词"""
        common_words = ['the', 'a', 'an', 'and', 'of', 'to', 'in', 'for', 'on', 'with', 
                        'that', 'this', 'is', 'are', 'was', 'were', 'by', 'at', 'from']
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 3 and w not in common_words]
        return keywords[:10]
    
    def is_api_available(self):
        """检查 API Key 是否有效"""
        debug_print(f"🔍 [API检查] API Key = {DEEPSEEK_API_KEY[:10] if DEEPSEEK_API_KEY else 'None'}... (长度: {len(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else 0})")
        
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == '':
            debug_print("❌ [API检查] API Key 为空")
            return False
        if len(DEEPSEEK_API_KEY) < 10:
            debug_print(f"❌ [API检查] API Key 长度不足: {len(DEEPSEEK_API_KEY)}")
            return False
        if DEEPSEEK_API_KEY == 'your-api-key-here':
            debug_print("❌ [API检查] API Key 是占位符")
            return False
        
        debug_print("✅ [API检查] API Key 有效，将尝试调用")
        return True
    
    def call_deepseek_api(self, prompt, context):
        """调用 DeepSeek API"""
        debug_print("🌐 [API调用] 正在连接 DeepSeek API...")
        debug_print(f"📝 [API调用] 问题: {prompt[:80]}...")
        
        try:
            full_prompt = f"""你是一个专业的学术论文助手。请基于以下信息回答用户问题。

=== 当前上下文 ===
{context}

=== 用户问题 ===
{prompt}

要求：
1. 回答要准确、简洁、有帮助
2. 如果上下文中有相关论文，请引用具体论文
3. 使用中文回答
4. 控制在400字以内"""
            
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": full_prompt}],
                "max_tokens": 800,
                "temperature": 0.7
            }
            
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
            
            debug_print(f"📡 [API调用] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()["choices"][0]["message"]["content"]
                debug_print("✅ [API调用] 成功！返回内容长度: " + str(len(result)))
                return result
            else:
                error_msg = response.json().get('error', {}).get('message', '未知错误')
                debug_print(f"❌ [API调用] 失败: {error_msg}")
                return None
        except Exception as e:
            debug_print(f"❌ [API调用] 异常: {e}")
            return None
    
    def local_answer_recommend(self, papers):
        """本地回答：推荐论文"""
        if papers and len(papers) > 0:
            paper = papers[0]
            innovations = self.extract_innovation(paper['summary'], paper['title'])
            innovation_text = ""
            if innovations:
                innovation_text = f"\n\n✨ **创新点**：{innovations[0]}"
            
            return f"""📚 **论文推荐**

**《{paper['title']}》**
📅 发表于 {paper['published']}
✍️ 作者：{', '.join(paper['authors'][:3])}
📝 摘要：{paper['summary'][:400]}...{innovation_text}

🔗 PDF链接：{paper['pdf_url']}

💡 **为什么推荐这篇？**
这篇论文来自{paper['published'][:4]}年，关注前沿领域，具有较好的参考价值。"""
        return "📚 请先搜索一些论文（例如：deep learning），然后我可以为您推荐最相关的一篇。"
    
    def local_answer_summary(self, papers):
        """本地回答：论文总结"""
        if papers and len(papers) > 0:
            paper = papers[0]
            innovations = self.extract_innovation(paper['summary'], paper['title'])
            
            summary_text = f"""📝 **论文总结**

**《{paper['title']}》**

📋 **摘要**：
{paper['summary'][:600]}...

✨ **创新点分析**："""
            if innovations:
                for i, inno in enumerate(innovations[:2], 1):
                    summary_text += f"\n{i}. {inno}"
            else:
                summary_text += "\n该论文在方法或应用方面有独到之处。"
            
            summary_text += f"\n\n📅 发表于 {paper['published']}"
            return summary_text
        return "📝 请先点击一篇论文（论文列表中的卡片），我可以帮您总结该论文的内容。"
    
    def local_answer_innovation(self, papers):
        """本地回答：创新点分析"""
        if papers and len(papers) > 0:
            paper = papers[0]
            innovations = self.extract_innovation(paper['summary'], paper['title'])
            
            result = f"""✨ **创新点分析**

**《{paper['title']}》**

"""
            if innovations:
                for i, inno in enumerate(innovations, 1):
                    result += f"{i}. {inno}\n\n"
            else:
                result += "该论文的创新点主要体现在：\n"
                result += "1. 提出了新的方法或框架\n"
                result += "2. 在实验验证方面有充分论证\n"
                result += "3. 相关代码/数据已公开（如适用）\n"
            
            result += f"\n📅 发表于 {paper['published']}\n"
            result += f"🔗 PDF：{paper['pdf_url']}"
            return result
        return "🔍 请先搜索并选择一篇论文，我可以为您分析其创新点。"
    
    def local_answer_review(self, papers, topic):
        """本地回答：生成文献综述"""
        return self.generate_literature_review(papers, topic)
    
    def local_answer_trend(self):
        """本地回答：研究趋势"""
        return """📊 **当前AI研究热点**

🔥 **热门方向**：
- 大语言模型 (LLM) 与提示工程
- 多模态学习 (视觉-语言模型)
- 具身智能与机器人
- AI for Science (科学发现)
- 扩散模型与生成式AI

📈 **趋势分析**：
近三个月，大语言模型相关论文占比最高，多模态学习增长最快。

💡 **建议**：
- 搜索 "large language model" 获取LLM论文
- 搜索 "multimodal" 获取多模态论文"""
    
    def local_answer_general(self, question):
        """本地回答：通用问题（API失败时的降级方案）"""
        return f"⚠️ API 暂时不可用。\n\n您的问题：{question}\n\n请稍后重试，或检查 API 余额。"
    
    def smart_answer(self, question, context=""):
        """智能问答入口：优先使用 API，失败时降级到本地"""
        context_papers = papers_db.get('latest', [])
        
        # 构建完整上下文
        full_context = context
        if context_papers:
            full_context += f"当前搜索结果中有 {len(context_papers)} 篇论文。"
            if len(context_papers) > 0:
                full_context += f"第一篇论文标题：《{context_papers[0]['title']}》"
                full_context += f"摘要：{context_papers[0]['summary'][:300]}"
        
        debug_print("="*50)
        debug_print(f"📨 [问答请求] 问题: {question[:100]}")
        debug_print("="*50)
        
        # ========== 优先使用 API ==========
        debug_print("🌐 [路由] 优先尝试使用 API")
        
        if self.is_api_available():
            debug_print("🚀 [决策] 将尝试使用 DeepSeek API")
            api_result = self.call_deepseek_api(question, full_context)
            if api_result:
                debug_print("🎉 [决策] API 调用成功，返回 API 回答")
                debug_print("="*50)
                return api_result
            else:
                debug_print("⚠️ [决策] API 调用失败，降级到本地回答")
        else:
            debug_print("💡 [决策] API 不可用，使用本地回答")
        
        # ========== API 失败后的降级方案 ==========
        q_lower = question.lower()
        
        # 根据问题类型选择合适的本地回答
        if any(kw in q_lower for kw in ['推荐', 'recommend']):
            debug_print("📚 [降级] 使用本地推荐回答")
            result = self.local_answer_recommend(context_papers)
        elif any(kw in q_lower for kw in ['总结', 'summarize']):
            debug_print("📚 [降级] 使用本地总结回答")
            result = self.local_answer_summary(context_papers)
        elif any(kw in q_lower for kw in ['创新点', 'innovation']):
            debug_print("📚 [降级] 使用本地创新点回答")
            result = self.local_answer_innovation(context_papers)
        elif any(kw in q_lower for kw in ['趋势', '热点']):
            debug_print("📚 [降级] 使用本地趋势回答")
            result = self.local_answer_trend()
        else:
            debug_print("📚 [降级] 使用本地通用回答")
            result = self.local_answer_general(question)
        
        debug_print("="*50)
        return result


# =====================================================
# 创建 assistant 实例和路由
# =====================================================
assistant = ImprovedPaperAssistant()

@app.route('/')
def index():
    return render_template('readingindex.html')

@app.route('/api/search', methods=['POST'])
def search_papers():
    data = request.json
    query = data.get('query', '')
    max_results = data.get('max_results', 20)
    sort_by = data.get('sort_by', 'relevance')
    
    papers = assistant.search_papers(query, max_results, sort_by)
    papers_db['latest'] = papers
    return jsonify({'papers': papers, 'count': len(papers)})

@app.route('/api/latest', methods=['POST'])
def get_latest_papers():
    data = request.json
    field = data.get('field', 'cs.AI')
    days = data.get('days', 7)
    
    papers = assistant.get_latest_papers_by_field(field, days)
    papers_db['latest'] = papers
    return jsonify({'papers': papers, 'count': len(papers), 'field': field})

@app.route('/api/my-feed', methods=['POST'])
def get_my_feed():
    papers = assistant.get_papers_by_subscription()
    papers_db['latest'] = papers
    return jsonify({'papers': papers, 'count': len(papers)})

@app.route('/api/summarize', methods=['POST'])
def summarize_paper():
    data = request.json
    content = data.get('content', '')
    title = data.get('title', '论文')
    
    summary = assistant.smart_answer(f"总结论文《{title}》", content[:2000])
    return jsonify({'summary': summary})

@app.route('/api/innovation', methods=['POST'])
def analyze_innovation():
    data = request.json
    content = data.get('content', '')
    title = data.get('title', '论文')
    
    innovation = assistant.smart_answer(f"分析论文《{title}》的创新点", content[:2000])
    return jsonify({'innovation': innovation})

@app.route('/api/literature-review', methods=['POST'])
def literature_review():
    data = request.json
    topic = data.get('topic', '人工智能')
    papers = papers_db.get('latest', [])
    
    review = assistant.generate_literature_review(papers, topic)
    return jsonify({'review': review})

@app.route('/api/question', methods=['POST'])
def ask_question():
    data = request.json
    question = data.get('question', '')
    
    answer = assistant.smart_answer(question, "")
    return jsonify({'answer': answer})

@app.route('/api/trends', methods=['POST'])
def get_trends():
    trends = {
        'hot_topics': ['大语言模型', '多模态学习', '计算机视觉', '具身智能'],
        'emerging_fields': ['扩散模型', 'AI for Science', 'Agent'],
        'publication_trend': 'AI领域论文发表量持续增长'
    }
    return jsonify(trends)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
