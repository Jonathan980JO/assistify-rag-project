'use client'

import { useState, useRef } from 'react'
import { Upload, Trash2, FileText, Search, Download, Eye, Loader2 } from 'lucide-react'

interface Document {
  id: string
  name: string
  size: string
  uploadedAt: string
  type: 'pdf' | 'txt' | 'doc'
  embedding: number
}

const mockDocuments: Document[] = [
  {
    id: '1',
    name: 'API Documentation.pdf',
    size: '2.4 MB',
    uploadedAt: '2024-06-20',
    type: 'pdf',
    embedding: 1024,
  },
  {
    id: '2',
    name: 'User Guide.pdf',
    size: '1.8 MB',
    uploadedAt: '2024-06-19',
    type: 'pdf',
    embedding: 512,
  },
  {
    id: '3',
    name: 'FAQ.txt',
    size: '0.3 MB',
    uploadedAt: '2024-06-18',
    type: 'txt',
    embedding: 128,
  },
  {
    id: '4',
    name: 'Technical Specs.doc',
    size: '0.9 MB',
    uploadedAt: '2024-06-17',
    type: 'doc',
    embedding: 256,
  },
]

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<Document[]>(mockDocuments)
  const [searchTerm, setSearchTerm] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const filteredDocs = documents.filter((doc) =>
    doc.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(e.type === 'dragenter' || e.type === 'dragover')
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleFiles = async (files: FileList) => {
    setUploading(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 1500))

      Array.from(files).forEach((file) => {
        const newDoc: Document = {
          id: String(documents.length + 1),
          name: file.name,
          size: (file.size / 1024 / 1024).toFixed(2) + ' MB',
          uploadedAt: new Date().toISOString().split('T')[0],
          type: file.name.split('.').pop() as 'pdf' | 'txt' | 'doc',
          embedding: Math.floor(Math.random() * 1000) + 128,
        }
        setDocuments((prev) => [newDoc, ...prev])
      })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = (id: string) => {
    if (window.confirm('Are you sure you want to delete this document?')) {
      setDocuments((prev) => prev.filter((doc) => doc.id !== id))
    }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(e.target.files)
    }
  }

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'pdf':
        return '📄'
      case 'doc':
        return '📋'
      default:
        return '📝'
    }
  }

  const totalEmbeddings = documents.reduce((sum, doc) => sum + doc.embedding, 0)

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#fafaff] mb-2">Knowledge Base</h1>
        <p className="text-[#9ca3af]">Manage RAG documents and embeddings for AI responses</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-4">
          <p className="text-[#9ca3af] text-sm mb-2">Total Documents</p>
          <p className="text-3xl font-bold text-[#fafaff]">{documents.length}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-4">
          <p className="text-[#9ca3af] text-sm mb-2">Total Embeddings</p>
          <p className="text-3xl font-bold text-[#10a37f]">{totalEmbeddings}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-4">
          <p className="text-[#9ca3af] text-sm mb-2">Storage Used</p>
          <p className="text-3xl font-bold text-[#2563eb]">
            {(
              documents.reduce(
                (sum, doc) => sum + parseFloat(doc.size),
                0
              )
            ).toFixed(1)}{' '}
            MB
          </p>
        </div>
      </div>

      {/* Upload Area */}
      <div
        className={`border-2 border-dashed rounded-lg p-12 mb-8 text-center cursor-pointer transition-colors ${
          dragActive
            ? 'border-[#10a37f] bg-[#10a37f]/5'
            : 'border-[#333333] bg-[#2b2b2b] hover:border-[#10a37f]/50'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileInput}
          className="hidden"
          accept=".pdf,.txt,.doc,.docx"
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-[#10a37f] animate-spin" />
            <p className="text-[#fafaff] font-medium">Uploading and embedding...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Upload className="w-8 h-8 text-[#10a37f]" />
            <div>
              <p className="text-[#fafaff] font-medium">
                Drag files here or click to browse
              </p>
              <p className="text-[#9ca3af] text-sm">
                Supported formats: PDF, DOC, TXT (Max 10 MB each)
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="mb-8">
        <div className="relative">
          <Search className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
          />
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#333333] bg-[#232323]">
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Document
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Size
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Embeddings
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Uploaded
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredDocs.length > 0 ? (
                filteredDocs.map((doc) => (
                  <tr
                    key={doc.id}
                    className="border-b border-[#333333] hover:bg-[#2b2b2b] transition-colors"
                  >
                    <td className="px-6 py-4 text-sm">
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{getFileIcon(doc.type)}</span>
                        <span className="font-medium text-[#fafaff]">{doc.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#9ca3af]">{doc.size}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className="px-3 py-1 bg-[#10a37f]/10 text-[#10a37f] rounded-full text-xs font-semibold">
                        {doc.embedding}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#9ca3af]">{doc.uploadedAt}</td>
                    <td className="px-6 py-4 text-sm">
                      <div className="flex items-center gap-2">
                        <button className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-[#2563eb] transition-colors">
                          <Eye className="w-4 h-4" />
                        </button>
                        <button className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-[#2563eb] transition-colors">
                          <Download className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-[#9ca3af]">
                    No documents found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
