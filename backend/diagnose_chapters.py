#!/usr/bin/env python3
"""
Diagnostic: Check PDF extraction for Chapter 7 and 10
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from PyPDF2 import PdfReader
import re

pdf_path = Path(__file__).parent / "assets" / "37f3c4f4_Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf"

print("=" * 80)
print(f"CHAPTER 7 & 10 EXTRACTION DIAGNOSTICS")
print("=" * 80)

reader = PdfReader(str(pdf_path))

# Find all chapter headings and their pages
chapter_pattern = re.compile(r'^\s*chapter\s+(\d+)\b', re.IGNORECASE | re.MULTILINE)

chapter_pages = {}
for page_idx, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ""
    matches = chapter_pattern.findall(text.lower())
    for match in matches:
        chapter_num = match
        if chapter_num not in chapter_pages:
            chapter_pages[chapter_num] = []
        chapter_pages[chapter_num].append(page_idx)

print(f"\nChapters found in PDF:")
for ch_num in sorted(chapter_pages.keys(), key=int):
    pages = chapter_pages[ch_num]
    print(f"  Chapter {ch_num:2s}: pages {pages[0]:3d} - {pages[-1]:3d} ({len(pages):3d} pages)")

print(f"\n{'='*80}")
print("CHAPTER 7 CONTENT ANALYSIS")
print(f"{'='*80}")

if '7' in chapter_pages:
    pages_list = chapter_pages['7']
    print(f"Pages: {pages_list}")
    
    # Extract all text for Chapter 7
    ch7_text = ""
    for page_idx in range(pages_list[0] - 1, pages_list[-1]):
        text = reader.pages[page_idx].extract_text() or ""
        ch7_text += f"[PAGE {page_idx + 1}]\n{text}\n"
    
    # Count non-whitespace content
    words = ch7_text.split()
    chars = len(ch7_text)
    paragraphs = len([p for p in ch7_text.split('\n\n') if p.strip() and len(p.strip()) > 50])
    
    print(f"  Total characters: {chars:,}")
    print(f"  Total words: {len(words):,}")
    print(f"  Paragraphs (>50 chars): {paragraphs}")
    
    print(f"\nFirst 500 chars of Chapter 7:")
    print(f"  {ch7_text[:500]}")
else:
    print("❌ Chapter 7 not found in PDF")

print(f"\n{'='*80}")
print("CHAPTER 10 CONTENT ANALYSIS")
print(f"{'='*80}")

if '10' in chapter_pages:
    pages_list = chapter_pages['10']
    print(f"Pages: {pages_list}")
    
    # Extract all text for Chapter 10
    ch10_text = ""
    for page_idx in range(pages_list[0] - 1, pages_list[-1]):
        text = reader.pages[page_idx].extract_text() or ""
        ch10_text += f"[PAGE {page_idx + 1}]\n{text}\n"
    
    # Count non-whitespace content
    words = ch10_text.split()
    chars = len(ch10_text)
    paragraphs = len([p for p in ch10_text.split('\n\n') if p.strip() and len(p.strip()) > 50])
    
    print(f"  Total characters: {chars:,}")
    print(f"  Total words: {len(words):,}")
    print(f"  Paragraphs (>50 chars): {paragraphs}")
    
    print(f"\nFirst 500 chars of Chapter 10:")
    print(f"  {ch10_text[:500]}")
else:
    print("❌ Chapter 10 not found in PDF")

print(f"\n{'='*80}")
print("ALL CHAPTERS SUMMARY")
print(f"{'='*80}")
for ch_num in sorted(chapter_pages.keys(), key=int):
    pages_list = chapter_pages[ch_num]
    start_page = pages_list[0]
    end_page = pages_list[-1]
    
    ch_text = ""
    for page_idx in range(start_page - 1, min(end_page, len(reader.pages))):
        text = reader.pages[page_idx].extract_text() or ""
        ch_text += text
    
    words = len(ch_text.split())
    print(f"  Chapter {ch_num:2s}: pages {start_page:3d}-{end_page:3d}, {words:6,} words")
