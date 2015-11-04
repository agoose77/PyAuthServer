#include <unordered_map>
#include <vector>

#include <boost/python.hpp>
using namespace boost::python;



class PriorityQueueElement
{
public:
	PriorityQueueElement(float score_, object obj_, long hash_) : score(score_), obj(obj_), hash(hash_), removed(false){};

	float score;
	object obj;
	bool removed;
	long hash;

	static bool compare(PriorityQueueElement* e1, PriorityQueueElement* e2)
	{
		return e1->score > e2->score;
	};
};


class PriorityQueue
{
public:
	PriorityQueue();
	~PriorityQueue();
	
	void add(object obj, float score);
	void add(object obj, int score);

	object pop();
	void remove(object obj);

	bool contains(object obj);
	bool has_items();
	list as_list();

private:
	typedef std::unordered_map<long, PriorityQueueElement*> T_HASH_DICT;
	T_HASH_DICT m_map;
	std::vector<PriorityQueueElement*> m_elements;

};
