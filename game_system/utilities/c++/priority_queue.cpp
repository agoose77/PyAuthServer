// priority_queue.cpp : Defines the exported functions for the DLL application.
//

#include "stdafx.h"
#include "priority_queue.h"

#include <algorithm>
#include <string>


PriorityQueue::PriorityQueue()
{
}

PriorityQueue::~PriorityQueue()
{
}

void PriorityQueue::add(object obj, float score)
{
	// Calculate hash and save for pop
	long hash = PyObject_Hash(obj.ptr());

	// Create element
	PriorityQueueElement* element = new PriorityQueueElement(score, obj, hash);

	m_map[hash] = element;

	m_elements.push_back(element);
	std::push_heap(m_elements.begin(), m_elements.end(), PriorityQueueElement::compare);

}

void PriorityQueue::add(object obj, int score)
{
	add(obj, (float)score);
}


void PriorityQueue::remove(object obj)
{
	long hash = PyObject_Hash(obj.ptr());

	T_HASH_DICT::iterator it = m_map.find(hash);

	if (it == m_map.end())
	{
		// error occurred
		puts("Not found!");
		return;
	}

	PriorityQueueElement* element = it->second;

	m_map.erase(it);
	element->removed = true;
}

object PriorityQueue::pop()
{
	object obj = object();

	if (!has_items())
		return obj;

	while (true)
	{
		std::pop_heap(m_elements.begin(), m_elements.end(), PriorityQueueElement::compare);

		PriorityQueueElement* element = m_elements.back();
		m_elements.pop_back();

		// If already removed
		bool exists = !element->removed;

		// Get object
		obj = element->obj;

		if (exists)
		{
			// Erase from map
			T_HASH_DICT::iterator it = m_map.find(element->hash);
			m_map.erase(it);
		}

		// Delete element
		delete element;

		if (exists)
			break;
	}

	return obj;
}


bool PriorityQueue::has_items()
{
	return !m_map.empty();
}


bool PriorityQueue::contains(object obj)
{
	long hash = PyObject_Hash(obj.ptr());

	T_HASH_DICT::iterator it = m_map.find(hash);
	return it != m_map.end();
}

list PriorityQueue::as_list()
{
	list elements;
	T_HASH_DICT::iterator it;

	for (it = m_map.begin(); it != m_map.end(); ++it)
	{
		object obj = it->second->obj;
		elements.append(obj);
	}

	return elements;
}


BOOST_PYTHON_MODULE(priority_queue)
{
	void (PriorityQueue::*add1)(object, float) = &PriorityQueue::add;
	void (PriorityQueue::*add2)(object, int) = &PriorityQueue::add;

	class_<PriorityQueue>("PriorityQueue")
		.def("add", add1)
		.def("add", add2)
		.def("pop", &PriorityQueue::pop)
		.def("remove", &PriorityQueue::remove)
		.def("__contains__", &PriorityQueue::contains)
		.def("__bool__", &PriorityQueue::has_items)
		.def("to_list", &PriorityQueue::as_list)
		;
}