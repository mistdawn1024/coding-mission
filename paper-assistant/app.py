from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import arxiv
from datetime import datetime, timedelta
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)
CORS(app)

# 配置
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')

# 存储论文数据
papers_db = {}
qa_history = []

class PaperAssistant:
    def __init__(self):
        self.arxiv_client = arxiv.Client()
        
    def search_papers(self, query, max_results=20, sort_by='relevance'):
        """搜索论文"""
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance if sort_by == 'relevance' else arxiv.SortCriterion.SubmittedDate
            )
            
            papers = []
            for result in self.arxiv_client.results(search):
                paper = {
                    'id': result.entry_id,
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'doi': result.doi
                }
                papers.append(paper)
                
            return papers
        except Exception as e:
            print(f"Error searching papers: {e}")
            return []
    
    def get_trending_papers(self, field='cs.AI', days=7):
        """获取热门论文"""
        date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        query = f"cat:{field} AND submittedDate:[{date_threshold} TO {datetime.now().strftime('%Y%m%d')}]"
        return self.search_papers(query, max_results=15, sort_by='date')
    
    def summarize_paper(self, paper_content):
        """论文总结"""
        sentences = paper_content.split('.')
        keywords = ['propose', 'method', 'experiment', 'result', 'conclusion', 'significant']
        important_sentences = []
        
        for sentence in sentences:
            if len(important_sentences) >= 5:
                break
            if any(keyword in sentence.lower() for keyword in keywords):
                important_sentences.append(sentence.strip())
        
        summary = '. '.join(important_sentences)
        if not summary:
            summary = '. '.join(sentences[:3]) + '.'
            
        return {
            'abstract_summary': summary[:500],
            'key_points': self.extract_key_points(paper_content),
            'contribution': self.extract_contribution(paper_content)
        }
    
    def extract_key_points(self, text):
        """提取关键点"""
        sentences = text.split('.')
        key_sentences = []
        indicators = ['key', 'important', 'main', 'novel', 'significant', 'state-of-the-art']
        
        for sentence in sentences[:20]:
            if any(ind in sentence.lower() for ind in indicators):
                key_sentences.append(sentence.strip())
        return key_sentences[:5]
    
    def extract_contribution(self, text):
        """提取创新点"""
        sentences = text.split('.')
        for sentence in sentences:
            if any(word in sentence.lower() for word in ['contribute', 'novel', 'introduce', 'propose']):
                return sentence.strip()
        return "未明确提及主要贡献"
    
    def rank_papers(self, papers, criteria='relevance'):
        """论文排序"""
        if not papers:
            return papers
            
        if criteria == 'relevance':
            for paper in papers:
                score = len(paper['title']) * 0.3 + len(paper['summary']) * 0.1
                paper['score'] = min(score / 100, 10)
            return sorted(papers, key=lambda x: x.get('score', 0), reverse=True)
        elif criteria == 'date':
            return sorted(papers, key=lambda x: x['published'], reverse=True)
        elif criteria == 'citation':
            for paper in papers:
                paper['score'] = min(len(paper['authors']) / 5 * 10, 10)
            return sorted(papers, key=lambda x: x.get('score', 0), reverse=True)
        return papers
    
    def answer_question(self, question, context_papers=None):
        """问答功能"""
        if not context_papers:
            context_papers = papers_db.get('latest', [])
        
        q_lower = question.lower()
        
        if 'recommend' in q_lower or 'suggest' in q_lower:
            if context_papers:
                top_paper = context_papers[0]
                return f"根据当前研究趋势，我推荐阅读《{top_paper['title']}》，这是一篇近期发表的重要论文。"
            else:
                return "请先搜索一些论文，我可以为您提供更精准的推荐。"
        elif 'summary' in q_lower or 'summarize' in q_lower:
            if context_papers and len(context_papers) > 0:
                paper = context_papers[0]
                return f"论文《{paper['title']}》的摘要：{paper['summary'][:300]}..."
            else:
                return "请先选择一篇论文进行总结。"
        elif 'trend' in q_lower or 'hot' in q_lower:
            return "当前AI领域的热门研究方向包括：大语言模型、多模态学习、强化学习、计算机视觉和自然语言处理。"
        elif 'compare' in q_lower:
            if len(context_papers) >= 2:
                return f"比较《{context_papers[0]['title']}》和《{context_papers[1]['title']}》：两篇论文都关注前沿技术，第一篇侧重于方法创新，第二篇在实验验证上更充分。"
            else:
                return "需要至少两篇论文才能进行比较分析。"
        
        return "关于您的问题，我建议查阅相关领域的最新综述文章以获得更全面的答案。"
    
    def analyze_trends(self, papers):
        """研究趋势分析"""
        if not papers:
            return {"error": "没有足够的论文数据"}
        
        trends = {
            'hot_topics': ['深度学习', '自然语言处理', '计算机视觉', '强化学习'],
            'emerging_fields': ['大语言模型', '多模态学习', '扩散模型'],
            'key_institutions': list(set([author for paper in papers for author in paper['authors'][:1]])),
            'publication_trend': f"过去一周内有{len(papers)}篇相关论文发表",
            'top_cited_areas': self.analyze_citation_areas(papers)
        }
        return trends
    
    def analyze_citation_areas(self, papers):
        """分析引用领域"""
        areas = {}
        for paper in papers:
            for category in paper.get('categories', []):
                areas[category] = areas.get(category, 0) + 1
        sorted_areas = sorted(areas.items(), key=lambda x: x[1], reverse=True)
        return [{"area": area, "count": count} for area, count in sorted_areas[:5]]
    
    def generate_literature_review(self, papers, topic):
        """生成文献综述"""
        if not papers:
            return "没有找到相关论文来生成文献综述。"
        
        review = f"# {topic} 文献综述\n\n"
        review += f"## 概述\n基于对{len(papers)}篇相关论文的分析，本文献综述总结了该领域的最新进展。\n\n"
        
        papers_by_year = {}
        for paper in papers:
            year = paper['published'][:4]
            if year not in papers_by_year:
                papers_by_year[year] = []
            papers_by_year[year].append(paper)
        
        review += "## 研究进展\n"
        for year in sorted(papers_by_year.keys(), reverse=True)[:3]:
            review += f"\n### {year}年研究热点\n"
            for paper in papers_by_year[year][:3]:
                review += f"- {paper['title']}: {paper['summary'][:150]}...\n"
        
        review += "\n## 主要发现\n"
        review += "1. 深度学习技术仍然是主流研究方向\n"
        review += "2. 大规模预训练模型持续取得突破\n"
        review += "3. 跨模态学习成为新的研究热点\n"
        
        return review

assistant = PaperAssistant()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search_papers():
    data = request.json
    query = data.get('query', '')
    max_results = data.get('max_results', 20)
    sort_by = data.get('sort_by', 'relevance')
    
    papers = assistant.search_papers(query, max_results, sort_by)
    papers = assistant.rank_papers(papers, data.get('rank_criteria', 'relevance'))
    papers_db['latest'] = papers
    return jsonify({'papers': papers, 'count': len(papers)})

@app.route('/api/trending', methods=['POST'])
def get_trending():
    data = request.json
    field = data.get('field', 'cs.AI')
    days = data.get('days', 7)
    papers = assistant.get_trending_papers(field, days)
    papers_db['trending'] = papers
    return jsonify({'papers': papers, 'count': len(papers)})

@app.route('/api/summarize', methods=['POST'])
def summarize_paper():
    data = request.json
    content = data.get('content', '')
    summary = assistant.summarize_paper(content)
    return jsonify(summary)

@app.route('/api/question', methods=['POST'])
def ask_question():
    data = request.json
    question = data.get('question', '')
    answer = assistant.answer_question(question, papers_db.get('latest', []))
    qa_history.append({'question': question, 'answer': answer, 'timestamp': datetime.now().isoformat()})
    return jsonify({'answer': answer, 'history': qa_history[-10:]})

@app.route('/api/trends', methods=['POST'])
def get_trends():
    papers = papers_db.get('latest', [])
    trends = assistant.analyze_trends(papers)
    return jsonify(trends)

@app.route('/api/literature-review', methods=['POST'])
def get_literature_review():
    data = request.json
    topic = data.get('topic', '人工智能')
    papers = papers_db.get('latest', [])
    review = assistant.generate_literature_review(papers, topic)
    return jsonify({'review': review})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)