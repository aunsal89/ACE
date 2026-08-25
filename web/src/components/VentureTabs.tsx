import { useState } from 'react';

interface Project {
  id: string;
  body: string;
}

export default function VentureTabs({ projects }: { projects: Project[] }) {
  const [activeTab, setActiveTab] = useState(projects[0]?.id || '');

  return (
    <div className="mt-12">
      {/* Tabs Navigation */}
      <div className="flex space-x-2 border-b border-slate-800 mb-8 overflow-x-auto pb-2">
        {projects.map((project) => (
          <button
            key={project.id}
            onClick={() => setActiveTab(project.id)}
            className={`px-6 py-3 font-medium text-sm transition-all whitespace-nowrap rounded-t-lg ${
              activeTab === project.id
                ? 'bg-slate-800 text-amber-500 border-b-2 border-amber-500'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            {project.id === 'Project_AURA' ? 'Project AURA' : 
             project.id === 'Project_EduTrace' ? 'EduTrace' : project.id}
          </button>
        ))}
      </div>

      {/* Tabs Content */}
      <div className="relative min-h-[600px]">
        {projects.map((project) => (
          <div
            key={project.id}
            className={`transition-opacity duration-500 absolute inset-0 ${
              activeTab === project.id ? 'opacity-100 z-10 block relative' : 'opacity-0 z-0 hidden'
            }`}
          >
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 md:p-10 shadow-xl backdrop-blur-sm">
              <div 
                className="prose prose-invert prose-slate max-w-none prose-headings:text-slate-100 prose-a:text-amber-500 hover:prose-a:text-amber-400 prose-strong:text-white prose-code:text-amber-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:rounded prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800 prose-blockquote:border-amber-500 prose-blockquote:bg-slate-800/30 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-table:border-collapse prose-th:border prose-th:border-slate-700 prose-th:bg-slate-800 prose-th:p-2 prose-td:border prose-td:border-slate-800 prose-td:p-2"
                dangerouslySetInnerHTML={{ __html: project.body }} 
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
