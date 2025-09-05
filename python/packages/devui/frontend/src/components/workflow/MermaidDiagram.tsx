import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

interface MermaidDiagramProps {
  diagram: string;
  activeExecutors?: string[];
  className?: string;
}

export function MermaidDiagram({ 
  diagram, 
  activeExecutors = [], 
  className = '' 
}: MermaidDiagramProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const diagramId = useRef(`mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);

  // Initialize mermaid once
  useEffect(() => {
    if (!isInitialized) {
      mermaid.initialize({ 
        startOnLoad: false, 
        theme: 'base',
        themeVariables: {
          primaryColor: '#3b82f6',
          primaryTextColor: '#1f2937',
          primaryBorderColor: '#3b82f6',
          lineColor: '#6b7280',
          secondaryColor: '#f3f4f6',
          tertiaryColor: '#ffffff',
        },
        flowchart: {
          htmlLabels: true,
          curve: 'basis'
        }
      });
      setIsInitialized(true);
    }
  }, [isInitialized]);

  // Render diagram and apply highlighting
  useEffect(() => {
    if (!isInitialized || !ref.current || !diagram.trim()) {
      return;
    }

    const renderDiagram = async () => {
      try {
        const { svg } = await mermaid.render(diagramId.current, diagram);
        if (ref.current) {
          ref.current.innerHTML = svg;
          
          // Apply active highlighting
          applyActiveHighlighting();
        }
      } catch (error) {
        console.error('Error rendering Mermaid diagram:', error);
        if (ref.current) {
          ref.current.innerHTML = `
            <div class="text-red-500 p-4 border border-red-200 rounded">
              <p class="font-medium">Error rendering workflow diagram</p>
              <p class="text-sm mt-1">Please check the console for details.</p>
            </div>
          `;
        }
      }
    };

    renderDiagram();
  }, [isInitialized, diagram, activeExecutors]);

  const applyActiveHighlighting = () => {
    if (!ref.current) return;

    // Remove previous highlighting
    const previousActive = ref.current.querySelectorAll('.active-executor');
    previousActive.forEach(el => el.classList.remove('active-executor'));

    // Apply new highlighting
    activeExecutors.forEach(executorId => {
      // Try different selectors to find the node
      const selectors = [
        `[id*="${executorId}"]`,
        `g[id*="${executorId}"]`,
        `.node[id*="${executorId}"]`,
        `text:contains("${executorId}")`,
        `[class*="${executorId}"]`
      ];

      for (const selector of selectors) {
        try {
          const elements = ref.current!.querySelectorAll(selector);
          elements.forEach(element => {
            // Find the parent node group if we're on a text element
            let nodeElement = element;
            if (element.tagName === 'text' || element.tagName === 'tspan') {
              const parentNode = element.closest('g.node') || element.closest('g[class*="node"]') || element.parentElement;
              if (parentNode) {
                nodeElement = parentNode;
              }
            }
            
            nodeElement.classList.add('active-executor');
          });

          if (elements.length > 0) {
            break; // Found and highlighted, move to next executor
          }
        } catch (e) {
          // Some selectors might fail, continue to next
          continue;
        }
      }
    });
  };

  if (!diagram.trim()) {
    return (
      <div className={`p-4 text-gray-500 text-center ${className}`}>
        No workflow diagram available
      </div>
    );
  }

  return (
    <div 
      ref={ref} 
      className={`mermaid-container ${className}`}
      style={{ minHeight: '200px' }}
    />
  );
}